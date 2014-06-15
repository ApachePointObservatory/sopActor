"""sopActor masterThread"""
import Queue, threading
import sys, time

from sopActor import *
import sopActor
import sopActor.myGlobals as myGlobals
from opscore.utility.qstr import qstr
from sopActor import MultiCommand

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

class SopPrecondition(Precondition):
    """
    This class is used to pass preconditions for a command to
    MultiCmd.  Only if required() returns True is the command actually
    scheduled and then run.
    """

    def __init__(self, queueName, msgId=None, timeout=None, **kwargs):
        Precondition.__init__(self, queueName, msgId, timeout, **kwargs)
        self.queueName = queueName

    def required(self):
        """
        If the system is not in the desired state, return True, otherwise False.
        
        Thus, self.required() will tell you whether you have to run the 
        command to get the system into the desired state.
        Also accounts for lamp warm-up time, so if the lamp was turned on 
        and enough time has passed, it is ok, but if not, require (the full time).
        """

        if self.queueName in myGlobals.warmupTime.keys():
            assert self.msgId == Msg.LAMP_ON

            isOn, timeSinceTransition = self.lampIsOn(self.queueName)
            # we want to turn them on
            if self.kwargs.get('on'):
                # we want the time since turn on
                if not isOn:
                    timeSinceTransition = 0
                warmupTime = myGlobals.warmupTime[self.queueName]
                # how long until they're ready
                delay = warmupTime - timeSinceTransition
                if delay > 0:
                    isOn = False
                    self.kwargs["delay"] = self.kwargs["duration"] = int(delay)
                # operation is required if they are not warmed up
                if not isOn:
                    return True
                else:
                    return False
            else:
                return isOn
        elif self.queueName in (sopActor.FFS,):
            assert self.msgId == Msg.FFS_MOVE
            # we want to open them
            if self.kwargs.get('open'):
                # operation is required if they are not already open
                return not self.ffsAreOpen()
            else:
                # operation is required if they are currently open
                return self.ffsAreOpen()

        elif self.queueName == sopActor.APOGEE and self.msgId == Msg.APOGEE_SHUTTER:
            # move if we are not where we want to be.
            return self.apogeeShutterIsOpen() != self.kwargs.get('open')
        elif self.queueName == sopActor.GUIDER:
            if self.msgId == Msg.DECENTER:
                # We have to turn on if decentering is off, and vice versa.
                if self.kwargs.get('on'):
                    return not self.isDecentered()
                else:
                    return self.isDecentered()
            elif self.msgId == Msg.MANGA_DITHER:
                dither = self.kwargs.get('dither')
                return not self.atCorrectMangaDither(dither)
            
        return True
    #
    # Commands to get state from e.g. the MCP
    #
    def ffsAreOpen(self):
        """
        Return True if flat field petals are open,
        False if they are closed, and None if indeterminate.
        """
        ffsStatus = myGlobals.actorState.models["mcp"].keyVarDict["ffsStatus"]

        open, closed = 0, 0
        for s in ffsStatus:
            if s == None:
                raise RuntimeError, "Unable to read FFS status"

            open += int(s[0])
            closed += int(s[1])

        if open == 8:
            return True
        elif closed == 8:
            return False
        else:
            return None

    def apogeeShutterIsOpen(self):
        """Return True if APOGEE shutter is open; False if closed, and None if indeterminate"""

        shutterStatus = myGlobals.actorState.models["apogee"].keyVarDict["shutterLimitSwitch"]

        if shutterStatus[0] and not shutterStatus[1]:
            return True
        elif shutterStatus[1] and not shutterStatus[0]:
            return False
        return None

    def lampIsOn(self, queueName):
        """
        Return (True iff some lamps are on, timeSinceTransition)
        The transition time can be used to determine if a lamp has been on long enough.
        """

        if queueName == sopActor.FF_LAMP:
            status = myGlobals.actorState.models["mcp"].keyVarDict["ffLamp"]
        elif queueName == sopActor.HGCD_LAMP:
            status = myGlobals.actorState.models["mcp"].keyVarDict["hgCdLamp"]
        elif queueName == sopActor.NE_LAMP:
            status = myGlobals.actorState.models["mcp"].keyVarDict["neLamp"]
        elif queueName == sopActor.UV_LAMP:
            return myGlobals.actorState.models["mcp"].keyVarDict["uvLampCommandedOn"][0], 0
        elif queueName == sopActor.WHT_LAMP:
            return myGlobals.actorState.models["mcp"].keyVarDict["whtLampCommandedOn"][0], 0
        else:
            print "Unknown lamp queue %s" % queueName
            return False, 0

        if status == None:
            raise RuntimeError, ("Unable to read %s lamp status" % queueName)

        on = 0
        for i in status:
            on += i

        return (True if on == 4 else False), (time.time() - status.timestamp)
    
    def isDecentered(self):
        """Return true if the guider currently has decenter mode active."""
        decenter = myGlobals.actorState.models["guider"].keyVarDict["decenter"]
        return decenter[1]

    def atCorrectMangaDither(self,newDither):
        """Return true if the guider currently is at the correct mangaDither position."""
        dither = myGlobals.actorState.models["guider"].keyVarDict["mangaDither"][0]
        return newDither == dither

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

# how long it takes to do various things
ffsDuration = 10                        # move the FFS
flushDuration = 25                      # flush the chips prior to an exposure
guiderReadoutDuration = 1               # readout the guider
hartmannDuration = 240                  # take a Hartmann sequence and move the collimators
readoutDuration = 90                    # read the BOSS chips
guiderDecenterDuration = 30             # Applying decenters could take as long as the longest reasonable guider exposure

class SopMultiCommand(MultiCommand):
    """A MultiCommand for sop that knows about how long sop commands take to execute"""

    def __init__(self, cmd, timeout, label, *args, **kwargs):
        MultiCommand.__init__(self, cmd, timeout, label, *args, **kwargs)
        pass

    def setMsgDuration(self, queueName, msg):
        """Set msg's expected duration in seconds"""

        if msg.type == Msg.FFS_MOVE:
            msg.duration = ffsDuration
        elif msg.type == Msg.EXPOSE:
            msg.duration = 0

            if queueName == sopActor.GUIDER:
                msg.duration += msg.expTime
                msg.duration += guiderReadoutDuration
            elif queueName == sopActor.BOSS:
                if msg.expTime >= 0:
                    msg.duration += flushDuration
                    msg.duration += msg.expTime
                if msg.readout:
                    msg.duration += readoutDuration
        elif msg.type == Msg.HARTMANN:
            msg.duration = hartmannDuration

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

def doLamps(cmd, actorState, FF=False, Ne=False, HgCd=False, WHT=False, UV=False,
            openFFS=None, openHartmann=None):
    """
    Turn each lamp on (True) or off (False),
    and open (True), close (False), or do not change (None) the flat field screen,
    and open (True) the Hartmanns.
    """

    multiCmd = SopMultiCommand(cmd, actorState.timeout, ".doLamps")

    multiCmd.append(sopActor.FF_LAMP  , Msg.LAMP_ON, on=FF)
    multiCmd.append(sopActor.HGCD_LAMP, Msg.LAMP_ON, on=Ne)
    multiCmd.append(sopActor.NE_LAMP  , Msg.LAMP_ON, on=HgCd)
    multiCmd.append(sopActor.WHT_LAMP , Msg.LAMP_ON, on=WHT)
    multiCmd.append(sopActor.UV_LAMP  , Msg.LAMP_ON, on=UV)
    if openFFS is not None:
        multiCmd.append(sopActor.FFS, Msg.FFS_MOVE, open=openFFS)
    #
    # There's no Hartmann thread, so just open them synchronously for now.  This should be rare.
    #
    if openHartmann is not None:
        cmdVar = actorState.actor.cmdr.call(actor="boss", forUserCmd=cmd,
                                            cmdStr=("hartmann out"), keyVars=[], timeLim=actorState.timeout)

        if cmdVar.didFail:
            cmd.warn('text="Failed to take Hartmann mask out"')
            return False

    return multiCmd.run()

#
# Helpers for dealing with lamps and FFS
#

# TBD: It'd be nice to have a way to unify the precondition and non-precondition
# calls. I previously tried to be clever with *args/**kwargs, but to no avail.

def prep_for_science(multiCmd,precondition=False):
    """Prepare for science exposure, by making sure lamps off and FFS open."""
    if precondition:
        multiCmd.append(SopPrecondition(sopActor.FFS, Msg.FFS_MOVE, open=True))
    else:
        multiCmd.append(sopActor.FFS, Msg.FFS_MOVE, open=True)
    prep_lamps_off(multiCmd,precondition)

def prep_lamps_off(multiCmd,precondition=False):
    """Prepare for something needing darkness, by turning off all lamps."""
    if precondition:
        multiCmd.append(SopPrecondition(sopActor.WHT_LAMP , Msg.LAMP_ON,  on=False))
        multiCmd.append(SopPrecondition(sopActor.UV_LAMP  , Msg.LAMP_ON,  on=False))
        multiCmd.append(SopPrecondition(sopActor.FF_LAMP  , Msg.LAMP_ON,  on=False))
        multiCmd.append(SopPrecondition(sopActor.HGCD_LAMP, Msg.LAMP_ON,  on=False))
        multiCmd.append(SopPrecondition(sopActor.NE_LAMP  , Msg.LAMP_ON,  on=False))
    else:
        multiCmd.append(sopActor.WHT_LAMP , Msg.LAMP_ON,  on=False)
        multiCmd.append(sopActor.UV_LAMP  , Msg.LAMP_ON,  on=False)
        multiCmd.append(sopActor.FF_LAMP  , Msg.LAMP_ON,  on=False)
        multiCmd.append(sopActor.HGCD_LAMP, Msg.LAMP_ON,  on=False)
        multiCmd.append(sopActor.NE_LAMP  , Msg.LAMP_ON,  on=False)

def prep_for_arc(multiCmd,precondition=False):
    """Prepare for an arc/hartmann, by closing the FFS and turning on arc lamps."""
    if precondition:
        multiCmd.append(SopPrecondition(sopActor.FFS      , Msg.FFS_MOVE, open=False))
        multiCmd.append(SopPrecondition(sopActor.WHT_LAMP , Msg.LAMP_ON, on=False))
        multiCmd.append(SopPrecondition(sopActor.UV_LAMP  , Msg.LAMP_ON, on=False))
        multiCmd.append(SopPrecondition(sopActor.FF_LAMP  , Msg.LAMP_ON, on=False))
        multiCmd.append(SopPrecondition(sopActor.HGCD_LAMP, Msg.LAMP_ON, on=True))
        multiCmd.append(SopPrecondition(sopActor.NE_LAMP  , Msg.LAMP_ON, on=True))
    else:
        multiCmd.append(sopActor.FFS      , Msg.FFS_MOVE, open=False)
        multiCmd.append(sopActor.WHT_LAMP , Msg.LAMP_ON, on=False)
        multiCmd.append(sopActor.UV_LAMP  , Msg.LAMP_ON, on=False)
        multiCmd.append(sopActor.FF_LAMP  , Msg.LAMP_ON, on=False)
        multiCmd.append(sopActor.HGCD_LAMP, Msg.LAMP_ON, on=True)
        multiCmd.append(sopActor.NE_LAMP  , Msg.LAMP_ON, on=True)
        
def prep_quick_hartmann(multiCmd):
    """Prepare for quick Hartmanns, which don't need the HgCd lamps fully warm."""
    multiCmd.append(SopPrecondition(sopActor.FFS      , Msg.FFS_MOVE, open=False))
    multiCmd.append(SopPrecondition(sopActor.WHT_LAMP , Msg.LAMP_ON, on=False))
    multiCmd.append(SopPrecondition(sopActor.UV_LAMP  , Msg.LAMP_ON, on=False))
    multiCmd.append(SopPrecondition(sopActor.FF_LAMP  , Msg.LAMP_ON, on=False))
    multiCmd.append(sopActor.HGCD_LAMP, Msg.LAMP_ON, on=True) # intentional!
    multiCmd.append(SopPrecondition(sopActor.NE_LAMP  , Msg.LAMP_ON, on=True))

def prep_for_flat(multiCmd,precondition=False):
    """Prepare for a flat, by closing the FFS and turning on flat lamps."""
    if precondition:
        multiCmd.append(SopPrecondition(sopActor.FFS, Msg.FFS_MOVE, open=False))
    else:
        multiCmd.append(sopActor.FFS, Msg.FFS_MOVE, open=False)
    prep_lamps_for_flat(multiCmd,precondition)

def prep_lamps_for_flat(multiCmd,precondition=False):
    """Prepare for a flat by turning the flat lamps on, and the others off."""
    if precondition:
        multiCmd.append(SopPrecondition(sopActor.WHT_LAMP , Msg.LAMP_ON, on=False))
        multiCmd.append(SopPrecondition(sopActor.UV_LAMP  , Msg.LAMP_ON, on=False))
        multiCmd.append(SopPrecondition(sopActor.FF_LAMP  , Msg.LAMP_ON, on=True))
        multiCmd.append(SopPrecondition(sopActor.HGCD_LAMP, Msg.LAMP_ON, on=False))
        multiCmd.append(SopPrecondition(sopActor.NE_LAMP  , Msg.LAMP_ON, on=False))
    else:
        multiCmd.append(sopActor.WHT_LAMP , Msg.LAMP_ON, on=False)
        multiCmd.append(sopActor.UV_LAMP  , Msg.LAMP_ON, on=False)
        multiCmd.append(sopActor.FF_LAMP  , Msg.LAMP_ON, on=True)
        multiCmd.append(sopActor.HGCD_LAMP, Msg.LAMP_ON, on=False)
        multiCmd.append(sopActor.NE_LAMP  , Msg.LAMP_ON, on=False)

def prep_apogee_shutter(multiCmd,open=True):
    """Open or close the APOGEE shutter, as a precondition."""
    multiCmd.append(SopPrecondition(sopActor.APOGEE, Msg.APOGEE_SHUTTER, open=open))

def prep_guider_decenter_on(multiCmd):
    """Prepare for MaNGA dithers by activating decentered guiding."""
    multiCmd.append(SopPrecondition(sopActor.GUIDER, Msg.DECENTER, on=True))

def prep_guider_decenter_off(multiCmd):
    """Prepare for on-center guiding by de-activating decentered guiding."""
    multiCmd.append(SopPrecondition(sopActor.GUIDER, Msg.DECENTER, on=False))

def prep_manga_dither(multiCmd, dither='C', precondition=False):
    """Prepare for MaNGA exposures by dithering the guider."""
    prep_guider_decenter_on(multiCmd)
    if precondition:
        multiCmd.append(SopPrecondition(sopActor.GUIDER, Msg.MANGA_DITHER, dither=dither, timeout=guiderDecenterDuration))
    else:
        multiCmd.append(sopActor.GUIDER, Msg.MANGA_DITHER, dither=dither, timeout=guiderDecenterDuration)

#
# Helpers for handling messages and running commands.
#

def preprocess_msg(msg):
    """Tells the message sender that we've started, and return useful fields."""
    msg.cmdState.setCommandState('running')
    msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=True)
    return msg.cmd,msg.cmdState,msg.actorState

def finish_command(cmd,cmdState,actorState,finishMsg="All Done!"):
    """Properly finish this command as fail or finish."""
    if actorState.aborting:
        cmdState.setCommandState('aborted')
        cmd.fail('text="%s was aborted"'%cmdState.name)
    else:
        cmdState.setCommandState('done')
        cmd.finish('text="%s"'%finishMsg)

def fail_command(cmd, cmdState, failMsg, longFailMsg='', finish=True):
    """
    Properly fail a command, send appropriate messages, return False.
    Because this fails the cmd, no further signals should be sent on this cmd.
    E.g. this is designed to be used in this idiom:
    if not multiCmd.run():
        return fail_command()
    """
    if not longFailMsg:
        longFailMsg = failMsg.capitalize()
    cmdState.setCommandState('failed', stateText=failMsg)
    if finish:
        cmd.fail('text="%s"'%longFailMsg)
    else:
        cmd.error('text="%s"'%longFailMsg)
    return False

def handle_multiCmd(multiCmd, cmd, cmdState, stageName, failMsg, longFailMsg='', finish=True):
    """
    Run a multiCmd and handle an error with a "fail" message.
    Returns True if the command was successful, False otherwise:
    If the command fails, we fail the cmd, so ensure you don't send furhter
    msgs on this cmd.
    """
    if not multiCmd.run():
        cmdState.setStageState(stageName, 'failed')
        return fail_command(cmd, cmdState, failMsg, longFailMsg, finish=finish)
    else:
        cmdState.setStageState(stageName, 'done')
        return True

def update_exp_counts(cmdState,expType):
    """Update the counts of exposure numbers done and remaining."""
    if expType == "bias":
        cmdState.nBiasDone += 1
    elif expType == "dark":
        cmdState.nDarkDone += 1
    elif expType == "flat":
        cmdState.nFlatDone += 1
    elif expType == "arc":
        cmdState.nArcDone += 1
    else:
        return False
    return True

def is_gang_at_cart(cmd, cmdState, actorState):
    """Fail, and return False if the gang is not at the cart, else return True."""
    if not actorState.apogeeGang.atCartridge():
        failMsg = "gang connector is not at the cartridge!"
        longFailMsg = "Not taking APOGEE exposures: %s"%failMsg
        return fail_command(cmd, cmdState, failMsg, longFailMsg)
    else:
        return True

#
# The actual SOP commands, and sub-commands.
#

def guider_start(cmd, cmdState, actorState, finish=True):
    """Prepare telescope to start guiding and turn the guider on."""
    cmdState.setStageState("guider", "running")
    multiCmd = SopMultiCommand(cmd, actorState.timeout + cmdState.guiderTime,
                               cmdState.name+".guider")
    
    multiCmd.append(sopActor.GUIDER, Msg.START, on=True,
                    expTime=cmdState.guiderTime, clearCorrections=True)
    prep_for_science(multiCmd, precondition=True)
    prep_guider_decenter_off(multiCmd)
    
    failMsg = "failed to start the guider"
    if not handle_multiCmd(multiCmd, cmd, cmdState, 'guider', failMsg, finish=finish):
        return False
    
    show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand="gotoField")
    return True
#...

def guider_flat(cmd, cmdState, actorState, stageName, apogeeShutter=False):
    """Take a guider flat, checking and closing the apogeeShutter if necessary."""
    guiderDelay = 20
    multiCmd = SopMultiCommand(cmd, actorState.timeout + guiderDelay, '.'.join((cmdState.name+stageName,'.guiderFlat')))
    if apogeeShutter:
        prep_apogee_shutter(multiCmd,open=False)
    prep_for_flat(multiCmd,precondition=True)
    multiCmd.append(sopActor.GUIDER, Msg.EXPOSE,expTime=cmdState.guiderFlatTime, expType="flat")
    if not handle_multiCmd(multiCmd,cmd,cmdState,stageName,"Failed to take a guider flat"):
        return False
    show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    return True
#...

def deactivate_guider_decenter(cmd, cmdState, actorState, stageName):
    """Prepare for non-MaNGA observations by disabling guider decenter mode."""
    # no label for this, as it doesn't need the full stageState output.
    multiCmd = SopMultiCommand(cmd, actorState.timeout, '')
    prep_guider_decenter_off(multiCmd)
    if not handle_multiCmd(multiCmd, cmd, cmdState, stageName, 'failed to disable decentered guide mode.', finish=False):
        return False
    return True

def apogee_dome_flat(cmd, cmdState, actorState, multiCmd, failMsg="failed to take APOGEE flat"):
    """
    Take an APOGEE dome flat: shutter open, FFS closed, FFlamp on very briefly.
    Doesn't "finish", because it is used in the middle of goto_gang_change;
    Return True if success, fail the cmd and return False if not.
    """

    if not is_gang_at_cart(cmd, cmdState, actorState):
        return False

    prep_apogee_shutter(multiCmd,open=True)
    multiCmd.append(SopPrecondition(sopActor.FFS, Msg.FFS_MOVE, open=False))
    multiCmd.append(sopActor.APOGEE_SCRIPT, Msg.POST_FLAT, cmdState=cmdState)
    if not handle_multiCmd(multiCmd, cmd, cmdState, 'domeFlat', failMsg, finish=True):
        return False
    else:
        return True
#...

def do_boss_science(cmd, cmdState, actorState):
    """Start a BOSS science sequence."""
    
    finishMsg = "Your Nobel Prize is a little closer!"
    failMsg = ""            # message to use if we've failed
    stageName = 'expose'
    while cmdState.nExpLeft > 0:
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=stageName)
        expTime = cmdState.expTime
        multiCmd = SopMultiCommand(cmd,
                                   flushDuration + expTime + readoutDuration + actorState.timeout,
                                   '.'.join((cmdState.name,stageName)))

        multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                        expTime=expTime, expType="science", readout=True)
        prep_for_science(multiCmd,precondition=True)
        cmd.inform('text="Taking a BOSS science exposure"')

        if not multiCmd.run():
            failMsg = "Failed to take BOSS science exposure"
            break

        cmdState.nExpDone += 1
        cmdState.nExpLeft -= 1
    
    # Did we break out of that loop?
    if failMsg:
        return fail_command(cmd, cmdState, failMsg)
    finish_command(cmd,cmdState,actorState,finishMsg)
#...

def do_apogee_science(cmd, cmdState, actorState):
    """Start an APOGEE science sequence."""
    
    expType = cmdState.expType
    finishMsg = "Your Nobel Prize is a little closer!"
    failMsg = ""            # message to use if we've failed
    stageName = 'expose'
    while cmdState.index < len(cmdState.exposureSeq):
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)

        expTime = cmdState.expTime
        newDither = cmdState.exposureSeq[cmdState.index]
        currentDither = actorState.models['apogee'].keyVarDict["ditherPosition"][1]
        # Per ticket #1756, APOGEE now does not want dither move requests
        # unless necessary, except at the start of an exposure sequence.
        if newDither == currentDither:
            dither = None
            cmd.inform('text="APOGEE dither already at desired position %s: not commanding move."'%(newDither))
        else:
            dither = newDither
            
        multiCmd = SopMultiCommand(cmd, expTime + actorState.timeout, cmdState.name)
        multiCmd.append(sopActor.APOGEE, Msg.EXPOSE,
                        expTime=expTime, dither=dither,
                        expType=expType, comment=cmdState.comment)
        prep_for_science(multiCmd,precondition=True)
        prep_apogee_shutter(multiCmd,open=True)

        text = 'taking %d of %d %s exposure'%(cmdState.index,len(cmdState.exposureSeq),expType)
        cmd.diag('text="%s"'%text)
        
        if not multiCmd.run():
            failMsg = "Failed to take an %s exposure" % (expType)
            break

        cmdState.index += 1
        seqIndex = (cmdState.index + len(cmdState.ditherSeq)-1) / len(cmdState.ditherSeq)
        cmdState.seqDone = seqIndex
    
    # Did we break out of that loop?
    if failMsg:
        return fail_command(cmd, cmdState, failMsg)
    finish_command(cmd,cmdState,actorState,finishMsg)
#...

def do_one_manga_dither(cmd, cmdState, actorState):
    """Start a single MaNGA dithered exposure."""
    
    dither = cmdState.dither
    expTime = cmdState.expTime
    readout = cmdState.readout
    
    show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    duration = flushDuration + expTime + actorState.timeout + guiderDecenterDuration
    if readout: 
        duration += readoutDuration
    multiCmd = SopMultiCommand(cmd, duration, cmdState.name+".expose")
    multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                    expTime=expTime, expType="science", readout=readout)
    prep_for_science(multiCmd, precondition=True)
    prep_manga_dither(multiCmd, dither=dither, precondition=True)
    
    return multiCmd.run()
#...

def do_manga_dither(cmd, cmdState, actorState):
    """Complete a single MaNGA dithered exposure."""
    finishMsg = "Your Nobel Prize is a little closer!"
    stageName = 'expose'
    cmdState.setStageState(stageName, 'running')
    if not do_one_manga_dither(cmd, cmdState, actorState):
        failMsg = "failed to take MaNGA science exposure"
        cmdState.setStageState(stageName, 'failed')
        deactivate_guider_decenter(cmd, cmdState, actorState, stageName)
        return fail_command(cmd, cmdState, failMsg)
    deactivate_guider_decenter(cmd, cmdState, actorState, stageName)
    finish_command(cmd,cmdState,actorState,finishMsg)
#...

def do_manga_sequence(cmd, cmdState, actorState):
    """Start a MaNGA dither sequence, consisting of multiple dither sets."""
    
    def do_cals_now(index):
        """Return True if it is time to do calibrations."""
        return index%arcExp == 0
    
    finishMsg = "Your Nobel Prize is a little closer!"
    failMsg = ""            # message to use if we've failed
    arcExp = 3 # number of exposures to take between arcs
    pendingReadout = False
    # set at start, and then update after each exposure.
    dither = cmdState.ditherSeq[cmdState.index]
    
    while cmdState.index < len(cmdState.ditherSeq):
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
        
        ditherState = CmdState.DoMangaDitherCmd()
        ditherState.expTime = cmdState.expTime
        ditherState.dither = dither
        ditherState.readout = False
        pendingReadout = True
        stageName = 'expose'
        cmdState.setStageState(stageName, 'running')
        if not do_one_manga_dither(cmd, ditherState, actorState):
            cmdState.setStageState(stageName, 'failed')
            failMsg = "failed one dither of a MaNGA dither sequence"
            break
        
        cmdState.index += 1
        
        multiCmd = SopMultiCommand(cmd, readoutDuration + actorState.timeout,
                                   cmdState.name+".readout")
        multiCmd.append(sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
        try:
            dither = cmdState.ditherSeq[cmdState.index]
            prep_manga_dither(multiCmd, dither=dither, precondition=False)
        except IndexError:
            # We're at the end, so don't need to move to new dither position.
            pass
        if do_cals_now(cmdState.index):
            multiCmd.append(sopActor.GUIDER, Msg.START, on=False)
            prep_for_arc(multiCmd, precondition=False)
        pendingReadout = False
        if not multiCmd.run():
            failMsg = "failed to readout exposure/change dither position"
            break
        
        # Take a mid-sequence calibration
        if do_cals_now(cmdState.index):
            stageName = 'calibs'
            cmdState.setStageState(stageName, 'running')
            expTime, expType = cmdState.arcTime, "arc"
            timeout = flushDuration + expTime + actorState.timeout + myGlobals.warmupTime[sopActor.HGCD_LAMP]
            multiCmd = SopMultiCommand(cmd, timeout, '.'.join((cmdState.name,stageName)))
            multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                            expTime=expTime, expType=expType, readout=False)
            prep_for_arc(multiCmd,precondition=True)
            # jkp TBD: use the below instead to make testing quicker!
            #prep_quick_hartmann(multiCmd)
            pendingReadout = True
            if not multiCmd.run():
                cmdState.setStageState(stageName, 'failed')
                failMsg = "failed arc after MaNGA dither set %d"%(cmdState.index//arcExp)
                break
            # Don't bother resetting guiding if we're all done.
            if cmdState.index < len(cmdState.ditherSeq):
                stageName = 'dither'
                # Readout arc, restart guider and reset lamps/ffs
                multiCmd = SopMultiCommand(cmd, actorState.timeout + readoutDuration,
                                           cmdState.name+".readout_restartGuider",
                                           sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
                multiCmd.append(sopActor.GUIDER, Msg.START, on=True)
                prep_for_science(multiCmd, precondition=False)
                prep_manga_dither(multiCmd, dither=dither, precondition=False)
                pendingReadout = False
                if not multiCmd.run():
                    cmdState.setStageState(stageName, 'failed')
                    failMsg = "failed to restart guider after MaNGA dither set %d post-calibs"%(cmdState.index//arcExp)
                    break
    show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    deactivate_guider_decenter(cmd, cmdState, actorState, 'dither')
    
    if pendingReadout:
        multiCmd = SopMultiCommand(cmd, actorState.timeout + readoutDuration,
                                   cmdState.name+".readout",
                                   sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
    else:
        multiCmd = SopMultiCommand(cmd, actorState.timeout,cmdState.name+'.cleanup')

    if failMsg:
        # handle the readout, but don't touch lamps, guider state, etc.
        if pendingReadout and not multiCmd.run():
            cmd.error('text="Failed to readout last exposure"')
        return fail_command(cmd, cmdState, failMsg)
    else:
        # Turn off lamps, since we're all done successfully.
        prep_lamps_off(multiCmd, precondition=False)
        if not multiCmd.run():
            return fail_command(cmd, cmdState, "Failed to readout last exposure or cleanup lamps/guider.")
    
    finish_command(cmd,cmdState,actorState,finishMsg)
#...

def do_boss_calibs(cmd, cmdState, actorState):
    """Start a BOSS instrument calibration sequence (flats, arcs, Hartmanns)"""
    
    ffsInitiallyOpen = SopPrecondition(None).ffsAreOpen()
    pendingReadout = False
    finishMsg = "Your calibration data are ready."
    failMsg = ""            # message to use if we've failed
    while cmdState.cals_remain():
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)

        if cmdState.nBiasDone < cmdState.nBias:
            expTime, expType = 0.0, "bias"
        elif cmdState.nDarkDone < cmdState.nDark:
            expTime, expType = cmdState.darkTime, "dark"
        elif cmdState.nFlatDone < cmdState.nFlat:
            expTime, expType = cmdState.flatTime, "flat"
        elif cmdState.nArcDone < cmdState.nArc:
            expTime, expType = cmdState.arcTime, "arc"
        else:
            failMsg = "Impossible condition: no exposures left after restart of while loop!"
            break

        if pendingReadout:
            # We will only get here if the next exposure to be taken is an arc or flat.
            # Darks/biases don't have pending readout: we don't want lamps
            # turning on while a dark is reading out!
            multiCmd = SopMultiCommand(cmd, actorState.timeout + readoutDuration,
                                        cmdState.name+".pendingReadout")
            multiCmd.append(sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
            pendingReadout = False
            if expType == "arc":
                prep_for_arc(multiCmd)
            elif expType == "flat":
                prep_for_flat(multiCmd)
            else:
                failMsg = "Impossible condition: exposure type is not arc or flat!"
                break
            
            if not multiCmd.run():
                failMsg = "Failed to prepare for %s" % expType
                break
        
        # Queue the exposure
        timeout = flushDuration + expTime + actorState.timeout
        if expType in ("bias", "dark"):
            timeout += readoutDuration

        # TBD: We need to let MultiCommand entries adjust the command timeout,
        # TBD: or have the preconditions take a separate timeout.
        # TBD: In the meanwhile fudge the longest case.
        if expType == "arc":
            timeout += myGlobals.warmupTime[sopActor.HGCD_LAMP]

        multiCmd = SopMultiCommand(cmd, timeout, cmdState.name+'.expose')
        
        if expType in ("bias", "dark"):
            pendingReadout = False
            multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                            expTime=expTime, expType=expType, readout=True)
            prep_lamps_off(multiCmd,precondition=True)
        elif expType == "flat":
            if cmdState.flatTime > 0:
                pendingReadout = True
                multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                                expTime=expTime, expType=expType, readout=False)
            if cmdState.guiderFlatTime > 0:
                cmd.inform('text="Taking a %gs guider flat exposure"' % (cmdState.guiderFlatTime))
                multiCmd.append(sopActor.GUIDER, Msg.EXPOSE,
                                expTime=cmdState.guiderFlatTime, expType="flat")
            prep_for_flat(multiCmd,precondition=True)
        elif expType == "arc":
            pendingReadout = True
            multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                            expTime=expTime, expType=expType, readout=False)
            prep_for_arc(multiCmd,precondition=True)
        else:
            failMsg = "Impossible condition: unknown exposure type when setting up for next exposure!"
            break

        cmd.inform('text="Taking %s %s exposure"' %
                    (("an" if expType[0] in ("a", "e", "i", "o", "u") else "a"), expType))
        if not multiCmd.run():
            failMsg = "Failed to take %s exposure" % expType
            break
        
        if not update_exp_counts(cmdState,expType):
            failMsg = "Impossible condition: unknown exposure type when determining exposures remaining!"
            break
    #endwhile
    
    # Did we break out of the while loop?
    if failMsg:
        if pendingReadout:
            if not SopMultiCommand(cmd, actorState.timeout + readoutDuration,
                                    cmdState.name+'.readoutCleanup',
                                    sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True).run():
                cmd.error('text="Failed to readout last exposure"')
        return fail_command(cmd, cmdState, failMsg)

    # Readout any pending data and return telescope to initial state
    multiCmd = SopMultiCommand(cmd,
                                actorState.timeout + (readoutDuration if pendingReadout else 0),
                                cmdState.name+'.readoutFinish')

    if pendingReadout:
        multiCmd.append(sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
        pendingReadout = False
    multiCmd.append(sopActor.FFS, Msg.FFS_MOVE, open=ffsInitiallyOpen)
    prep_lamps_off(multiCmd)
    
    failMsg = "telescope is in unknown state"
    longFailMsg = "Failed to restore telescope to pristine state"
    if not handle_multiCmd(multiCmd,cmd,cmdState,'cleanup',failMsg,longFailMsg):
        return

    finish_command(cmd,cmdState,actorState,finishMsg)
#...

def start_slew(cmd, cmdState, actorState, slewTimeout):
    """Prepare for the start of a slew. Returns the relevant multiCmd for precondition appending."""
    cmdState.setStageState('slew', 'running')
    multiCmd = SopMultiCommand(cmd, slewTimeout + actorState.timeout, cmdState.name+".slew")
    multiCmd.append(SopPrecondition(sopActor.TCC, Msg.AXIS_INIT)) # start with an axis init
    multiCmd.append(sopActor.TCC, Msg.SLEW, actorState=actorState,
                    ra=cmdState.ra, dec=cmdState.dec, rot=cmdState.rotang,
                    keepOffsets=cmdState.keepOffsets)
    return multiCmd

def _run_slew(cmd, cmdState, actorState, multiCmd):
    """To help with running a slew multiCmd."""
    if not multiCmd.run():
        failMsg = "Failed to close screens, warm up lamps, and slew to field"
        cmdState.setStageState('slew', 'failed')
        if actorState.tccState.badStat and not Bypass.get(name='axes'):
            cmd.warn('text="Some axis status is bad!!! Cannot slew!"')
        return fail_command(cmd, cmdState, 'slew', failMsg)
    else:
        return True

def goto_field_apogee(cmd, cmdState, actorState, slewTimeout):
    """Process a goto field sequence for an APOGEE plate."""
    
    if cmdState.doSlew:
        multiCmd = start_slew(cmd, cmdState, actorState, slewTimeout)
        # NOTE: the FFS should remain closed during APOGEE slews,
        # for fear of IR-bright things like Luna.
        multiCmd.append(sopActor.FFS, Msg.FFS_MOVE, open=False)
        if cmdState.doGuider and cmdState.doGuiderFlat:
            prep_apogee_shutter(multiCmd,open=False)
            prep_lamps_for_flat(multiCmd,precondition=True)
        
        if not _run_slew(cmd,cmdState,actorState,multiCmd):
            return False

    # For APOGEE plates (no gotofield calibs), take the guider flat while slewing.
    if cmdState.doGuider and cmdState.doGuiderFlat:
        guider_flat(cmd, cmdState, actorState, 'slew', apogeeShutter=True)
    
    if cmdState.doGuider:
        return guider_start(cmd, cmdState, actorState)
    
    return True
#...

def goto_field_boss(cmd, cmdState, actorState, slewTimeout):
    """Process a goto field sequence for a BOSS plate."""
    
    pendingReadout = False
    stageName = ''
    
    doGuiderFlat = True if (cmdState.doGuiderFlat and cmdState.doGuider and cmdState.guiderFlatTime > 0) else False
    doingCalibs = False
    if cmdState.doSlew:
        stageName = 'slew'
        multiCmd = start_slew(cmd, cmdState, actorState, slewTimeout)
        if cmdState.arcTime > 0 or cmdState.doHartmann:
            prep_for_arc(multiCmd)
        elif doGuiderFlat or cmdState.flatTime > 0:
            prep_for_flat(multiCmd)
        
        if not _run_slew(cmd,cmdState,actorState,multiCmd):
            return False
        
        cmdState.setStageState(stageName, 'done')
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    
    # We're on the field: start with a hartmann
    if cmdState.doHartmann:
        stageName = 'hartmann'
        hartmannDelay = 210
        cmdState.setStageState(stageName, "running")
        multiCmd = SopMultiCommand(cmd, actorState.timeout + hartmannDelay, cmdState.name+'.hartmann')
        prep_quick_hartmann(multiCmd)
        multiCmd.append(sopActor.BOSS, Msg.HARTMANN)
        if not handle_multiCmd(multiCmd,cmd,cmdState,stageName,"Failed to take hartmann sequence"):
            return False
        
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    
    # Calibs: arc then flat (and guider flat if we're going to guide)
    if cmdState.doCalibs:
        stageName = 'calibs'
        doingCalibs = True
        cmdState.setStageState(stageName, 'running')
        
        # Arcs first
        if cmdState.arcTime > 0:
            timeout = actorState.timeout + myGlobals.warmupTime[sopActor.HGCD_LAMP]
            multiCmd = SopMultiCommand(cmd, timeout, cmdState.name+'.calibs.arc')
            prep_for_arc(multiCmd,precondition=True)
            if not handle_multiCmd(multiCmd,cmd,cmdState,stageName,"Failed to prepare for arcs"):
                return False
            
            # Now take the exposure: separate from above so we can check to see
            # if the arc stage was aborted/cancelled/stopped before the exposure started.
            if cmdState.arcTime > 0:
                if SopMultiCommand(cmd, cmdState.arcTime + actorState.timeout,
                                    cmdState.name+'.calibs.arcExposure',
                                    sopActor.BOSS, Msg.EXPOSE,
                                    expTime=cmdState.arcTime, expType="arc", readout=False,).run():
                    pendingReadout = True
                    cmdState.didArc = True
                else:
                    cmdState.setStageState(stageName, 'failed')
                    return fail_command(cmd, cmdState, "failed to take arcs")
            show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    
        # Now the flats
        if cmdState.flatTime > 0:
            multiCmd = SopMultiCommand(cmd,
                                    actorState.timeout + (readoutDuration if pendingReadout else 0),
                                    cmdState.name+'.calibs.flats')
            if pendingReadout:
                multiCmd.append(sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
                pendingReadout = False
            
            if cmdState.flatTime > 0 or doGuiderFlat:
                prep_for_flat(multiCmd)
            if not handle_multiCmd(multiCmd,cmd,cmdState,'calibs',"Failed to prepare for flats"):
                return False
            
            # Now take the exposure, separate from the above to catch aborts/stops.
            if cmdState.flatTime > 0 or doGuiderFlat:
                multiCmd = SopMultiCommand(cmd, cmdState.flatTime + actorState.timeout + 30,
                                        cmdState.name+'.calibs.flatExposure')
            if cmdState.flatTime > 0:
                pendingReadout = True
                multiCmd.append(sopActor.BOSS, Msg.EXPOSE,
                                expTime=cmdState.flatTime, expType="flat", readout=False)
            # recheck these, incase the command was aborted or modified since we defined doGuiderFlat above.
            if cmdState.doGuider and cmdState.doGuiderFlat and cmdState.guiderFlatTime > 0:
                multiCmd.append(sopActor.GUIDER, Msg.EXPOSE,
                                expTime=cmdState.guiderFlatTime, expType="flat")
            if not multiCmd.run():
                if pendingReadout:
                    # readout the previous command
                    if not SopMultiCommand(cmd, actorState.timeout + readoutDuration,
                                        cmdState.name+'.calibs.flatReadout',
                                        sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True).run():
                        cmd.error("text='Failed to readout last exposure!'")
                cmdState.setStageState(stageName, 'failed')
                return fail_command(cmd, cmdState, 'failed to take flats')
            cmdState.didFlat = True
            cmdState.doGuiderFlat = False # since we just did it.
            show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    
    # Readout any pending data and prepare to guide
    if pendingReadout:
        readoutMultiCmd = SopMultiCommand(cmd, readoutDuration + actorState.timeout,
                                          cmdState.name+'.calibs.lastReadout')
        readoutMultiCmd.append(sopActor.BOSS, Msg.EXPOSE, expTime=-1, readout=True)
        pendingReadout = False
        readoutMultiCmd.start()
    else:
        if doingCalibs:
            cmdState.setStageState(stageName, 'done')
    
        readoutMultiCmd = None
    
    failedCmd = None
    if cmdState.doGuider:
        if cmdState.doGuiderFlat:
            if not guider_flat(cmd, cmdState, actorState, 'guider'):
                failedCmd = 'guider'
            cmdState.doGuiderFlat = False
        if not failedCmd:
            if not guider_start(cmd, cmdState, actorState, finish=False):
                failedCmd = 'guider'
    else:
        # Turn off lamps, since we're all done, successfully.
        cmdState.setStageState('cleanup', 'running')
        multiCmd = SopMultiCommand(cmd, actorState.timeout, cmdState.name+'.cleanup')
        prep_lamps_off(multiCmd, precondition=True)
        if not multiCmd.run():
            failedCmd = 'cleanup'
        else:
            cmdState.setStageState('cleanup', 'done')
    
    failMsg = ''
    # catch a guider or cleanup failure.
    if failedCmd is not None:
        cmdState.setStageState(failedCmd, 'failed')
        failMsg = ';'.join((failMsg,'failed to cleanup gotofield/start guiding'))

    # Catch the last readout's completion
    if readoutMultiCmd:
        if not readoutMultiCmd.finish():
            cmdState.setStageState(stageName, 'failed')
            failMsg = ';'.join((failMsg,'failed to readout last exposure'))
        else:
            cmdState.setStageState(stageName, 'done')

    if failMsg:
        return fail_command(cmd, cmdState, failMsg)
    
    # all done, everything succeeded!
    return True
#...

def goto_field(cmd, cmdState, actorState):
    """Start a goto field sequence, with behavior depending on the current survey."""
    
    # Slew to field
    slewTimeout = 180
    finishMsg = "On field."
    
    show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand="gotoField")
    
    if actorState.survey == sopActor.APOGEE:
        success = goto_field_apogee(cmd, cmdState, actorState, slewTimeout)
    elif actorState.survey == sopActor.BOSS or actorState.survey == sopActor.MANGA:
        success = goto_field_boss(cmd, cmdState, actorState, slewTimeout)
    
    # if not success: we've already failed the command.
    if success:
        finish_command(cmd,cmdState,actorState,finishMsg)

def goto_gang_change(cmd, cmdState, actorState):
    """
    Goto gang change position at requested altitude, taking a dome flat on
    the way if we have an APOGEE cartridge, and the gang is plugged into it.
    """
    
    finishMsg = "at gang change position"
    # Behavior varies depending on where the gang connector is.
    # doCals == True if we are on the cartridge.
    doCals = actorState.apogeeGang.atCartridge()
    multiCmd = MultiCommand(cmd, actorState.timeout + 100,
                            cmdState.name+".slew")
    cmdState.setStageState('slew', 'running')
    
    # TBD: SDSSIV: this should be a test based on 'APOGEE' in survey
    # or maybe based off of survey_mode? Will have to discuss with
    # APOGEE/MaNGA folks...
    if doCals and actorState.survey != sopActor.BOSS:
        cmd.inform('text="scheduling flat: %s %s"' % (doCals, actorState.survey))
        if not apogee_dome_flat(cmd, cmdState, actorState, multiCmd, failMsg="failed to take flat before gang change"):
            return
    else:
        # Close the FFS, to prevent excess light incase of slews past the moon, etc.
        multiCmd.append(SopPrecondition(sopActor.FFS, Msg.FFS_MOVE, open=False))
        gangAt = actorState.apogeeGang.getPos()
        cmd.inform('text="Skipping flat with %s and %s"' % (gangAt, actorState.survey))

    tccDict = actorState.models["tcc"].keyVarDict

    if doCals:              # Heading towards the instrument change pos.
        az = 121
        alt = cmdState.alt
        rot = 0

        # Try to move the rotator as far as we can while the altitude is moving.
        thisAlt = tccDict['axePos'][1]
        thisRot = tccDict['axePos'][2]
        dRot = rot-thisRot
        if dRot != 0:
            dAlt = alt-thisAlt
            dAltTime = abs(dAlt) / 1.5 #deg/sec
            dRotTime = abs(dRot) / 2.0 #deg/sec
            dCanRot = dRot * min(1.0, dAltTime/dRotTime)
            rot = thisRot + dCanRot
    else:                   # Nod up.
        # going to the commanded altitude, leaving az and rot where they are.
        az = tccDict['axePos'][0]
        alt = cmdState.alt
        rot = tccDict['axePos'][2]

    slewDuration = 60
    multiCmd = MultiCommand(cmd, slewDuration + actorState.timeout, None)

    # start with an axis init, in case the axes are not clear.
    multiCmd.append(SopPrecondition(sopActor.TCC, Msg.AXIS_INIT))
    # TBD: SDSSIV: this should be a test based on 'APOGEE' in survey
    # or maybe based off of survey_mode? Will have to discuss with
    # APOGEE/MaNGA folks...
    if actorState.survey == sopActor.APOGEE:
        # Precondition: we want the shutter to be closed during the slew.
        prep_apogee_shutter(multiCmd,open=False)
        # used to do darks on the way to the field.
        # multiCmd.append(sopActor.APOGEE_SCRIPT, Msg.APOGEE_PARK_DARKS)
    multiCmd.append(sopActor.TCC, Msg.SLEW, actorState=actorState, az=az, alt=alt, rot=rot)

    if not handle_multiCmd(multiCmd,cmd,cmdState,"slew","Failed to slew to gang change"):
        return

    finish_command(cmd,cmdState,actorState,finishMsg)
#...

def hartmann(cmd, cmdState, actorState):
    """Take two arc exposures with the left then the right Hartmann screens in."""
    ffsInitiallyOpen = SopPrecondition(None).ffsAreOpen()
    finishMsg = "Finished left/right Hartmann set."
    
    hartmannTime = myGlobals.warmupTime[sopActor.NE_LAMP] + readoutDuration
    show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    # Turn on the lamps before we do anything: this way, we turn them both on, but can 
    # start exposing right away, since we don't need the full amount of light.
    doLamps(cmd, actorState, HgCd=True, Ne=True, openFFS=False)
    for stageName in ('left','right'):
        cmdState.setStageState(stageName, 'running')
        multiCmd = SopMultiCommand(cmd, actorState.timeout + hartmannTime, '.'.join((cmdState.name,stageName)))
        multiCmd.append(sopActor.BOSS, Msg.SINGLE_HARTMANN, expTime=cmdState.expTime, mask=stageName)
        if not handle_multiCmd(multiCmd,cmd,cmdState,stageName,"Failed to take %s Hartmann"%stageName):
            return False
        show_status(cmdState.cmd, cmdState, actorState.actor, oneCommand=cmdState.name)
    
    # cleanup
    stageName = 'cleanup'
    cmdState.setStageState(stageName, 'running')
    multiCmd = SopMultiCommand(cmd, actorState.timeout, '.'.join((cmdState.name,'cleanup')))
    if ffsInitiallyOpen:
        cmd.inform('text="Restoring FFS to previous open state."')
        prep_for_science(multiCmd,precondition=True)
        failMsg = "Failed to open FFS/turn off lamps after Hartmanns"
    else:
        prep_lamps_off(multiCmd,precondition=True)
        failMsg = "Failed to turn off lamps after Hartmanns"
    if not handle_multiCmd(multiCmd,cmd,cmdState,stageName,failMsg):
        return False

    finish_command(cmd, cmdState, actorState, finishMsg)
#...

def show_status(cmd, cmdState, actor, oneCommand=""):
    """Output status of a new state or just one command."""
    if cmd:
        actor.commandSets["SopCmd"].status(cmd, threads=False, finish=False, oneCommand=oneCommand)

# Define the command that we use to communicate our state to e.g. STUI
def main(actor, queues):
    """Main loop for SOP master thread."""

    threadName = "master"
    timeout = myGlobals.actorState.timeout
    overhead = 150                      # overhead per exposure, minimum; seconds

    while True:
        try:
            msg = queues[MASTER].get(timeout=timeout)

            if msg.type == Msg.EXIT:
                if msg.cmd:
                    msg.cmd.inform("text=\"Exiting thread %s\"" % (threading.current_thread().name))

                return

            elif msg.type == Msg.DO_BOSS_CALIBS:
                cmd,cmdState,actorState = preprocess_msg(msg)
                do_boss_calibs(cmd, cmdState, actorState)

            elif msg.type == Msg.DO_BOSS_SCIENCE:
                cmd,cmdState,actorState = preprocess_msg(msg)
                do_boss_science(cmd, cmdState, actorState)
                      
            elif msg.type == Msg.DO_APOGEE_EXPOSURES:
                # Make sure we'd get light!
                if not is_gang_at_cart(msg):
                    continue
                cmd,cmdState,actorState = preprocess_msg(msg)
                do_apogee_science(cmd, cmdState, actorState)

            elif msg.type == Msg.DO_MANGA_DITHER:
                cmd,cmdState,actorState = preprocess_msg(msg)
                do_manga_dither(cmd, cmdState, actorState)
            
            elif msg.type == Msg.DO_MANGA_SEQUENCE:
                cmd,cmdState,actorState = preprocess_msg(msg)
                do_manga_sequence(cmd, cmdState, actorState)
            
            elif msg.type == Msg.GOTO_FIELD:
                cmd,cmdState,actorState = preprocess_msg(msg)
                goto_field(cmd, cmdState, actorState)
            
            elif msg.type == Msg.APOGEE_DOME_FLAT:
                cmd,cmdState,actorState = preprocess_msg(msg)
                name = 'apogeeDomeFlat'
                finishMsg = "Dome flat done."
                # 50 seconds is the read time for this exposure.
                multiCmd = MultiCommand(cmd, actorState.timeout + 50, name)
                # the dome flat command sends a fail msg if it fails.
                if apogee_dome_flat(cmd, cmdState, actorState, multiCmd):
                    finish_command(cmd, cmdState, actorState, finishMsg)

            elif msg.type == Msg.GOTO_GANG_CHANGE:
                cmd,cmdState,actorState = preprocess_msg(msg)
                goto_gang_change(cmd, cmdState, actorState)

            elif msg.type == Msg.HARTMANN:
                cmd,cmdState,actorState = preprocess_msg(msg)
                hartmann(cmd, cmdState, actorState)
            
            elif msg.type == Msg.DITHERED_FLAT:
                """Take a set of nStep dithered flats, moving the collimator by nTick between exposures"""

                cmd = msg.cmd
                actorState = msg.actorState

                expTime = msg.expTime
                spN = msg.spN
                nStep = msg.nStep
                nTick = msg.nTick

                if not doLamps(cmd, actorState, FF=True):
                    msg.replyQueue.put(Msg.EXPOSURE_FINISHED, cmd=cmd, success=False)
                    cmd.warn('text="Some lamps failed to turn on"')
                    continue

                success = True          # let's be optimistic
                moved = 0
                for i in range(nStep + 1):  # +1: final large move to get back to where we started
                    expose = True
                    if i == 0:
                        move = nTick*(nStep//2)
                    elif i == nStep:
                        move = -moved
                        expose = False
                    else:
                        move = -nTick

                    dA = dB = move
                    dC = -dA

                    for sp in spN:
                        cmdVar = actorState.actor.cmdr.call(actor="boss", forUserCmd=cmd,
                                                            cmdStr=("moveColl spec=%s a=%d b=%d c=%d" % (sp, dA, dB, dC)),
                                                            keyVars=[], timeLim=timeout)

                        if cmdVar.didFail:
                            cmd.warn('text="Failed to move collimator for %s"' % sp)
                            success = False
                            break

                    if not success:
                        break

                    moved += move
                    cmd.inform('text="After %dth collimator move: at %d"' % (i, moved))

                    if expose:
                        if False:
                            cmd.inform('text="XXXXX Not taking a %gs exposure"' % expTime)
                        else:
                            cmdVar = actorState.actor.cmdr.call(actor="boss", forUserCmd=cmd,
                                                                cmdStr=("exposure %s itime=%g" % ("flat", expTime)),
                                                                keyVars=[], timeLim=expTime + overhead)

                            if cmdVar.didFail:
                                cmd.warn('text="Failed to take %gs exposure"' % expTime)
                                cmd.warn('text="Moving collimators back to initial positions"')

                                dA = dB = -moved
                                dC = -dA

                                for sp in spN:
                                    cmdVar = actorState.actor.cmdr.call(actor="boss", forUserCmd=cmd,
                                                                        cmdStr=("moveColl spec=%s a=%d b=%d c=%d" % (sp, dA, dB, dC)),
                                                                        keyVars=[], timeLim=timeout)

                                    if cmdVar.didFail:
                                        cmd.warn('text="Failed to move collimator for %s back to initial position"' % sp)
                                        break

                                success = False
                                break

                doLamps(cmd, actorState)

                msg.replyQueue.put(Msg.EXPOSURE_FINISHED, cmd=cmd, success=success)

            elif msg.type == Msg.EXPOSURE_FINISHED:
                print '!!!!!!!!!!!!!!!!'
                if msg.success:
                    msg.cmd.finish()
                else:
                    msg.cmd.fail("")

            elif msg.type == Msg.STATUS:
                msg.cmd.inform('text="%s thread"' % threadName)
                msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=True)
            else:
                raise ValueError, ("Unknown message type %s" % (msg.type))
        except Queue.Empty:
            actor.bcast.diag('text="%s alive"' % threadName)
        except Exception, e:
            sopActor.handle_bad_exception(actor,e,threadName,msg)

