import Queue, threading
import math, numpy

from sopActor import *
import sopActor.myGlobals
from opscore.utility.qstr import qstr
from opscore.utility.tback import tback

def main(actor, queues):
    """Main loop for guider thread"""

    threadName = "guider"
    actorState = sopActor.myGlobals.actorState
    timeout = actorState.timeout

    while True:
        try:
            msg = queues[sopActor.GUIDER].get(timeout=timeout)

            if msg.type == Msg.EXIT:
                if msg.cmd:
                    msg.cmd.inform("text=\"Exiting thread %s\"" % (threading.current_thread().name))

                return

            elif msg.type == Msg.ENABLE:
                msg.cmd.respond("text=\"%s guiding on %s\"" %
                                (("enabling" if msg.on else "disabling"), msg.what))

                timeLim = 10
                cmdVar = actorState.actor.cmdr.call(actor="guider", forUserCmd=msg.cmd,
                                                    cmdStr=("%s %s" % (msg.what, "on" if msg.on else "off")),
                                                    keyVars=[], timeLim=timeLim)
                    
                msg.replyQueue.put(Msg.DONE, cmd=msg.cmd, success=not cmdVar.didFail)

            elif msg.type == Msg.START:
                msg.cmd.respond("text=\"%s guider\"" % (("starting" if msg.on else "stopping")))

                if msg.expTime > 0:
                    expTimeOpt = ("time=%g" % msg.expTime)
                else:
                    expTimeOpt = ""

                forceOpt = "force" if (hasattr(msg, 'force') and msg.force) else ""
                oneExposureOpt = "oneExposure" if (hasattr(msg, 'oneExposure') and msg.oneExposure) else ""
                    
                timeLim = msg.expTime   # seconds
                timeLim += 100
                cmdVar = actorState.actor.cmdr.call(actor="guider", forUserCmd=msg.cmd,
                                                    cmdStr="%s %s %s %s" % (("on" if msg.on else "off"),
                                                                       expTimeOpt, forceOpt, oneExposureOpt),
                                                    keyVars=[], timeLim=timeLim)
                    
                msg.replyQueue.put(Msg.DONE, cmd=msg.cmd, success=not cmdVar.didFail)


            elif msg.type == Msg.EXPOSE:
                msg.cmd.respond('text="starting guider flat"')

                if msg.expTime > 0:
                    expTimeOpt = ("time=%g" % msg.expTime)
                else:
                    expTimeOpt = ""

                timeLim = msg.expTime   # seconds
                timeLim += 100

                #guider flat is hardwired at 0.5 sec at present, so no expTimeOpt
                cmdVar = actorState.actor.cmdr.call(actor="guider", forUserCmd=msg.cmd,
                                                    keyVars=[], timeLim=timeLim)
                    
                msg.replyQueue.put(Msg.DONE, cmd=msg.cmd, success=not cmdVar.didFail)

            elif msg.type == Msg.STATUS:
                msg.cmd.inform('text="%s thread"' % threadName)
                msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=True)
            else:
                raise ValueError, ("Unknown message type %s" % msg.type)
        except Queue.Empty:
            actor.bcast.diag('text="%s alive"' % threadName)
        except Exception, e:
            errMsg = "Unexpected exception %s in sop %s thread" % (e, threadName)
            actor.bcast.warn('text="%s"' % errMsg)
            tback(errMsg, e)

            try:
                msg.replyQueue.put(Msg.EXIT, cmd=msg.cmd, success=False)
            except Exception, e:
                pass
