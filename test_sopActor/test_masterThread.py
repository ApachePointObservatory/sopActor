"""
Test the various commands in SOP masterThread
"""

import unittest

from actorcore import TestHelper
import sopTester

import sopActor
import sopActor.myGlobals as myGlobals
import sopActor.CmdState as CmdState

from sopActor import masterThread
from sopActor import bossThread
from sopActor import apogeeThread
from sopActor import guiderThread
from sopActor import gcameraThread
from sopActor import ffsThread
from sopActor import lampThreads
from sopActor import tccThread
from sopActor import scriptThread

# False for less printing, True for more printing
verbose = True
#verbose = False

class MasterThreadTester(sopTester.SopThreadTester,unittest.TestCase):
    """
    Tests for the various functions in sop masterThread, that were
    ripped out of the main loop during the bigCleanup...
    """
    def setUp(self):
        self.verbose = verbose
        self.useThreads = [("apogee",sopActor.APOGEE, apogeeThread.main),
                           ("apogeeScript",  sopActor.APOGEE_SCRIPT, apogeeThread.script_main),
                           ("boss",    sopActor.BOSS,     bossThread.main),
                           ("script",  sopActor.SCRIPT,   sopTester.FakeThread),
                           ("guider",  sopActor.GUIDER,   guiderThread.main),
                           ("gcamera", sopActor.GCAMERA,  sopTester.FakeThread),
                           ("ff",      sopActor.FF_LAMP,  lampThreads.ff_main),
                           ("hgcd",    sopActor.HGCD_LAMP,lampThreads.hgcd_main),
                           ("ne",      sopActor.NE_LAMP,  lampThreads.ne_main),
                           ("uv",      sopActor.UV_LAMP,  lampThreads.uv_main),
                           ("wht",     sopActor.WHT_LAMP, lampThreads.wht_main),
                           ("ffs",     sopActor.FFS,      ffsThread.main),
                           ("tcc",     sopActor.TCC,      tccThread.main),
                          ]
        super(MasterThreadTester,self).setUp()
        self.fail_on_no_cmd_calls = True # we need cmd_calls for all of these.


class TestGuider(MasterThreadTester):
    """guider_* tests"""
    def _guider_start(self,nCall,nInfo,nWarn,nErr,finish=False,didFail=False):
        """Helper for running guider start tests."""
        cmdState = CmdState.GotoFieldCmd()
        result = masterThread.guider_start(self.cmd, cmdState, myGlobals.actorState, "gotoField")
        self.assertEqual(result,not didFail)
        self._check_cmd(nCall, nInfo, nWarn, nErr, finish, didFail=didFail)
        
    def test_guider_start_ffsClosed(self):
        """ffs open, 3x axis clear, guider on"""
        self._guider_start(5,9,0,0)
    def test_guider_start_ffsOpen(self):
        """3x axis clear, guider on"""
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        self._guider_start(4,6,0,0)
    def test_guider_start_arcsOn(self):
        """ffs open, he off, hgcd off, 3x axis clear, guider on"""
        sopTester.updateModel('mcp',TestHelper.mcpState['arcs'])
        self._guider_start(7,9,0,0)
    def test_guider_start_flatsOn(self):
        """ffs open, flat off, 3x axis clear, guider on"""
        sopTester.updateModel('mcp',TestHelper.mcpState['flats'])
        self._guider_start(6,9,0,0)
    def test_guider_start_fails(self):
        self.cmd.failOn = "guider on time=5"
        self._guider_start(5,12,0,1,finish=True,didFail=True)

    def _guider_flat(self,nCall,nInfo,nWarn,nErr,finish=False,didFail=False):
        """Helper for running guider flat tests."""
        cmdState = CmdState.GotoFieldCmd()
        result = masterThread.guider_flat(self.cmd, cmdState, myGlobals.actorState, "guider")
        self.assertEqual(result,not didFail)
        self._check_cmd(nCall, nInfo, nWarn, nErr, finish, didFail=didFail)
    def test_guider_flat_ffsClosed(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        self._guider_flat(2,8,0,0)
    def test_guider_flat_ffsOpen(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        self._guider_flat(3,8,0,0)
    def test_guider_flat_fails(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        self.cmd.failOn = "guider flat time=0.5"
        self._guider_flat(2,11,0,0,finish=True,didFail=True)
    
    def _guider_flat_apogeeShutter(self,nCall,nInfo,nWarn,nErr,finish=False,didFail=False):
        """Helper for running guider flat tests that check the APOGEE shutter."""
        cmdState = CmdState.GotoFieldCmd()
        result = masterThread.guider_flat(self.cmd, cmdState, myGlobals.actorState, "guider", apogeeShutter=True)
        self.assertEqual(result,not didFail)
        self._check_cmd(nCall,nInfo,nWarn,nErr, finish, didFail=didFail)
    def test_guider_flat_apogeeShutter_open(self):
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        self._guider_flat_apogeeShutter(3,8,0,0)
    def test_guider_flat_apogeeShutter_closed(self):
        sopTester.updateModel('apogee',TestHelper.apogeeState['A_closed'])
        self._guider_flat_apogeeShutter(2,8,0,0)
        
    def _deactivate_guider_decenter(self,nCall,nInfo,nWarn,nErr, didFail=False):
        stageName = 'dither'
        cmdName = 'doMangaDither'
        cmdState = CmdState.DoMangaDitherCmd()
        result = masterThread.deactivate_guider_decenter(self.cmd, cmdState, myGlobals.actorState, stageName)
        self.assertEqual(result,not didFail)
        self._check_cmd(nCall, nInfo, nWarn, nErr, False, didFail=didFail)
    def test_deactivate_guider_decenter_on(self):
        """decenter off"""
        sopTester.updateModel('guider',TestHelper.guiderState['guiderOnDecenter'])
        self._deactivate_guider_decenter(1,4,0,0)
    def test_deactivate_guider_decenter_off(self):
        """(nothing: already off)"""
        self._deactivate_guider_decenter(0,2,0,0)
    def test_deactivate_guider_decenter_fails(self):
        """
        decenter off
        Will give cmd.error and stage=failed, but won't fail command.
        """
        sopTester.updateModel('guider',TestHelper.guiderState['guiderOnDecenter'])
        self.cmd.failOn="guider decenter off"
        self._deactivate_guider_decenter(1,7,0,1,didFail=True)

    
class TestGotoField(MasterThreadTester):
    """GotoField and slewing tests"""
    def test_start_slew(self):
        cmdState = CmdState.GotoFieldCmd()
        result = masterThread.start_slew(self.cmd, cmdState, myGlobals.actorState, self.timeout)
        self.assertIsInstance(result,sopActor.MultiCommand)
        self.assertEqual(result.timeout, self.timeout+myGlobals.actorState.timeout)
        self._check_cmd(0,1,0,0,False)
    
    def _goto_feld_apogee(self, nCall, nInfo, nWarn, nErr, cmdState):
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        masterThread.goto_field_apogee(self.cmd,cmdState,myGlobals.actorState,self.timeout)
        self._check_cmd(nCall, nInfo, nWarn, nErr, False)
    def test_goto_field_apogee(self):
        """
        FF on, axis status, axis init, slew, FF on, guider flat, FF off, open FFS
        3xguider axes off, guider on
        One warning from "in slew with halted=False slewing=False"
        """
        cmdState = CmdState.GotoFieldCmd()
        self._goto_feld_apogee(12,26,1,0,cmdState)
    def test_goto_field_apogee_no_guider(self):
        """
        axis status, axis init, slew
        One warning from "in slew with halted=False slewing=False"
        """
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doGuider = False
        self._goto_feld_apogee(3,9,1,0,cmdState)
    def test_goto_field_apogee_no_slew(self):
        """
        FF on, guider flat, FF off, open FFS
        3xguider axes off, guider on
        """
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doSlew = False
        self._goto_feld_apogee(8,17,0,0,cmdState)
    def test_goto_field_apogee_no_slew_decenter_off(self):
        """
        FF on, guider flat, FF off, open FFS
        guider decenter off, 3xguider axes off, guider on
        """
        sopTester.updateModel('guider',TestHelper.guiderState['guiderOnDecenter'])
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doSlew = False
        self._goto_feld_apogee(9,18,0,0,cmdState)

    def test_goto_field_apogee_no_slew_shutter_open(self):
        """
        shutter close, FF on, guider flat, FF off, open FFS
        3xguider axes off, guider on
        """
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doSlew = False
        self._goto_feld_apogee(9,17,0,0,cmdState)
    
    def _goto_field_boss(self, nCall, nInfo, nWarn, nErr, cmdState, finish=False, didFail=False):
        masterThread.goto_field_boss(self.cmd,cmdState,myGlobals.actorState,self.timeout)
        self._check_cmd(nCall, nInfo, nWarn, nErr, finish, didFail)
    def test_goto_field_boss_all(self):
        """
        see cmd_calls/TestGotoField.txt for command list.
        One warning from "in slew with halted=False slewing=False"
        """
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        self._goto_field_boss(25,58,1,0,cmdState)
    def test_goto_field_boss_slew(self):
        """
        axis status, axis init, slew
        One warning from "in slew with halted=False slewing=False"
        """
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doGuider = False
        cmdState.doHartmann = False
        cmdState.doCalibs = False
        cmdState.arcTime = 0
        cmdState.flatTime = 0
        self._goto_field_boss(3,15,1,0,cmdState)
    def test_goto_field_boss_hartmann(self):
        """
        ne on, hgcd on, ff off, doHartmann, ne off, hgcd off
        """
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doSlew = False
        cmdState.doCalibs = False
        cmdState.arcTime = 0
        cmdState.flatTime = 0
        cmdState.doGuider = False
        self._goto_field_boss(5,18,0,0,cmdState)
    def test_goto_field_boss_calibs(self):
        """
        see cmd_calls/TestGotoField.txt for command list.
        """
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doSlew = False
        cmdState.doHartmann = False
        cmdState.doGuider = False
        self._goto_field_boss(10,37,0,0,cmdState)
    def test_goto_field_boss_guider(self):
        """
        Start with decentered guiding on, to check that we clear it.
        ff on, guider flat, ff off, ffs open 3xguider axes off, decenter off, guider on
        """
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        sopTester.updateModel('guider',TestHelper.guiderState['guiderOnDecenter'])
        cmdState = CmdState.GotoFieldCmd()
        cmdState.doSlew = False
        cmdState.doHartmann = False
        cmdState.doCalibs = False
        cmdState.arcTime = 0
        cmdState.flatTime = 0
        self._goto_field_boss(9,18,0,0,cmdState)
    
    def test_goto_field_boss_flat_on_fails(self):
        """Fail on ff.on, but still readout the arc."""
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        self.cmd.failOn = "mcp ff.on"
        self._goto_field_boss(16,42,1,1,cmdState,didFail=True,finish=True)
    def test_goto_field_boss_ne_on_fails(self):
        """Fail on ne.on."""
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        self.cmd.failOn = "mcp ne.on"
        self._goto_field_boss(6,13,1,1,cmdState,didFail=True,finish=True)
    def test_goto_field_boss_sos_doHartmann_fails(self):
        """Fail on sos doHartmann."""
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        self.cmd.failOn = "sos doHartmann"
        self._goto_field_boss(9,23,1,1,cmdState,didFail=True,finish=True)
    def test_goto_field_boss_ffs_open_fails(self):
        """Fail on ffs.open, but still readout flat."""
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        self.cmd.failOn = "mcp ffs.open"
        self._goto_field_boss(21,64,2,1,cmdState,didFail=True,finish=True)
    
    def _goto_field_apogeemanga(self, nCall, nInfo, nWarn, nErr, cmdState, finish=False, didFail=False):
        masterThread.goto_field_apogeemanga(self.cmd,cmdState,myGlobals.actorState,self.timeout)
        self._check_cmd(nCall, nInfo, nWarn, nErr, finish, didFail)
    def test_goto_field_apogeemanga_all(self):
        """
        see cmd_calls/TestGotoField.txt for command list.
        One warning from "in slew with halted=False slewing=False"
        """
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        cmdState = CmdState.GotoFieldCmd()
        self._goto_field_apogeemanga(25,58,1,0,cmdState)

class TestHartmann(MasterThreadTester):
    """hartmann tests"""
    def _hartmann(self,nCall,nInfo,nWarn,nErr, finish=True, didFail=False):
        cmdState = CmdState.HartmannCmd()
        masterThread.hartmann(self.cmd,cmdState,myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,finish,didFail)
    def test_hartmann_open(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        self._hartmann(9,27,0,0)
    def test_hartmann_closed(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        self._hartmann(7,26,0,0)
    def test_hartmann_fails(self):
        self.cmd.failOn="boss exposure arc itime=4 hartmann=left"
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        self._hartmann(4,12,0,0,didFail=True)
    def test_hartmann_fails_cleanup(self):
        self.cmd.failOn="mcp ne.off"
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        self._hartmann(7,26,0,1,didFail=True)
        

class TestApogeeDomeFlat(MasterThreadTester):
    """apogee_dome_flat tests"""
    # NOTE: the cmd numbers here aren't right, because I haven't fully faked
    # the apogee utrReadState thing, so the fflamps don't get called on+off.
    # TBD: That would increase the nCalls in each of these by 2:
    #     One for ff.on and one for ff.off
    def _apogee_dome_flat(self,nCall,nInfo,nWarn,nErr, multiCmd, finish=False, didFail=False):
        cmdState = CmdState.DoApogeeDomeFlatCmd()
        result = masterThread.apogee_dome_flat(self.cmd, cmdState, myGlobals.actorState, multiCmd)
        self._check_cmd(nCall,nInfo,nWarn,nErr,finish,didFail)
        self.assertEqual(result, not didFail)
    def test_apogee_dome_flat_gang_change(self):
        """shutter open, FFS close, exposure +(ff on, ff off)"""
        name = 'apogeeDomeFlat'
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        multiCmd = sopActor.MultiCommand(self.cmd, myGlobals.actorState.timeout + 50, name)
        self._apogee_dome_flat(3,9,0,0, multiCmd)
    def test_apogee_dome_flat_enclosure(self):
        """shutter open, exposure +(ff on, ff off)"""
        name = 'apogeeDomeFlat'
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_parked'])
        multiCmd = sopActor.MultiCommand(self.cmd, myGlobals.actorState.timeout + 50, name)
        self._apogee_dome_flat(2,9,0,0, multiCmd)
    def test_apogee_dome_flat_enclosure_shutterOpen(self):
        """exposure +(ff on, ff off)"""
        name = 'apogeeDomeFlat'
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_parked'])
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        multiCmd = sopActor.MultiCommand(self.cmd, myGlobals.actorState.timeout + 50, name)
        self._apogee_dome_flat(1,6,0,0, multiCmd)
        
    def test_apogee_dome_flat_ffs_fails(self):
        """shutter open, ffs close->fail"""
        name = 'apogeeDomeFlat'
        self.cmd.failOn = "mcp ffs.close"
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        multiCmd = sopActor.MultiCommand(self.cmd, myGlobals.actorState.timeout + 50, name)
        self._apogee_dome_flat(2,10,1,0, multiCmd, finish=True, didFail=True)
    def test_apogee_dome_flat_gang_on_podium_fails(self):
        """fail immediately"""
        name = 'apogeeDomeFlat'
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        multiCmd = sopActor.MultiCommand(self.cmd, myGlobals.actorState.timeout + 50, name)
        self._apogee_dome_flat(0,3,0,0, multiCmd, finish=True, didFail=True)


class TestGotoGangChange(MasterThreadTester):
    """goto_gang_change tests"""
    # NOTE: the cmd numbers here aren't right, because I haven't fully faked
    # the apogee utrReadState thing, so the fflamps don't get called on+off.
    # TBD: That would increase the nCalls in each of these by 2:
    #     One for ff.on and one for ff.off
    def _goto_gang_change(self, nCall, nInfo, nWarn, nErr, finish=True, didFail=False):
        cmdState = CmdState.GotoGangChangeCmd()
        masterThread.goto_gang_change(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,finish,didFail)
    def test_goto_gang_change_apogee_open(self):
        """
        axis status, axis init, slew, FFS close, expose +(ff on, ff off)
        One warning from "in slew with halted=False slewing=False"
        """
        myGlobals.actorState.survey = sopActor.APOGEE
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        self._goto_gang_change(6, 19, 1, 0)
    def test_goto_gang_change_apogee_closed(self):
        """
        axis status, axis init, slew,
        shutter open, FFS close, expose +(ff on, ff off), shutter close
        One warning from "in slew with halted=False slewing=False"
        """
        myGlobals.actorState.survey = sopActor.APOGEE
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        sopTester.updateModel('apogee',TestHelper.apogeeState['A_closed'])
        self._goto_gang_change(7, 19, 1, 0)
    def test_goto_gang_change_apogee_gang_podium(self):
        """
        axis status, axis init, slew, shutter close
        One warning from "in slew with halted=False slewing=False"
        """
        myGlobals.actorState.survey = sopActor.APOGEE
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        sopTester.updateModel('mcp',TestHelper.mcpState['all_off'])
        self._goto_gang_change(4, 10, 1, 0)
    def test_goto_gang_change_boss(self):
        """
        axis status, axis init, slew
        One warning from "in slew with halted=False slewing=False"
        """
        myGlobals.actorState.survey = sopActor.BOSS
        self._goto_gang_change(3, 10, 1, 0)
        
    def test_goto_gang_change_apogee_fails_domeflat(self):
        """shutter open, FFS close, expose->fail"""
        myGlobals.actorState.survey = sopActor.APOGEE
        self.cmd.failOn = "apogee expose time=50.0 object=DomeFlat"
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        self._goto_gang_change(2, 13, 1, 0, didFail=True)
    def test_goto_gang_change_apogee_fails_slew(self):
        """
        ffs close, exposure, shutter close, axis status, axis init, slew->fail
        """
        self.cmd.failOn = "tcc axis init"
        myGlobals.actorState.survey = sopActor.APOGEE
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        self._goto_gang_change(5, 18, 0, 2, didFail=True)


class TestBossScience(MasterThreadTester):
    """do_boss_science tests"""
    def _do_boss_science(self, nCall, nInfo, nWarn, nErr, nExp=1):
        """Helper for boss science tests"""
        cmdState = CmdState.DoBossScienceCmd()
        cmdState.nExpLeft = nExp
        masterThread.do_boss_science(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,True)
        
    def test_do_boss_science(self):
        """One call per requested exposure"""
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        nExp = 2
        self._do_boss_science(nExp,14,0,0,nExp=nExp)


class TestApogeeScience(MasterThreadTester):
    """do_apogee_science tests"""
    def _do_apogee_science(self, nCall, nInfo, nWarn, nErr, ditherSeq='ABBA', seqCount=1):
        """Helper for boss science tests"""
        cmdState = CmdState.DoApogeeScienceCmd()
        cmdState.ditherSeq = ditherSeq
        cmdState.exposureSeq = ditherSeq * seqCount
        cmdState.seqCount = seqCount
        masterThread.do_apogee_science(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,True)
    def test_do_apogee_science(self):
        """open shutter, one call per exposure, dither moves"""
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_science'])
        sopTester.updateModel('apogee',TestHelper.apogeeState['A_closed'])
        ditherSeq = 'ABBA' # causes 2 dither moves: A->B, B->A
        seqCount = 1
        nCall = 1 + seqCount*len(ditherSeq) + 2*seqCount
        self._do_apogee_science(nCall,29,0,0,ditherSeq=ditherSeq,seqCount=seqCount)


class TestMangaScience(MasterThreadTester):
    """do_manga_* tests"""
    def _do_one_manga_dither(self, nCall, nInfo, nWarn, nErr, dither='N'):
        cmdState = CmdState.DoMangaDitherCmd()
        cmdState.dither = dither
        masterThread.do_one_manga_dither(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,False)
    def test_do_one_manga_dither(self):
        """gudier decenter, guider dither, boss exposure"""
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        dither = 'N'
        self._do_one_manga_dither(3,9,0,0,dither=dither)
    
    def _do_manga_dither(self, nCall, nInfo, nWarn, nErr, dither='N', didFail=False):
        cmdState = CmdState.DoMangaDitherCmd()
        cmdState.dither = dither
        masterThread.do_manga_dither(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,True,didFail=didFail)
    def test_do_manga_dither(self):
        """decenter on, guider dither, boss exposure, decenter off"""
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        dither = 'N'
        self._do_manga_dither(4,17,0,0,dither=dither)
    def test_do_manga_dither_fails_ffs(self):
        """decenter on, guider dither, ffs open->fail, decenter off (cleanup)"""
        self.cmd.failOn = "mcp ffs.open"
        dither = 'S'
        self._do_manga_dither(4,17,1,0,dither=dither, didFail=True)
    
    def _do_manga_sequence(self,nCall,nInfo,nWarn,nErr,count,dithers='NSE'):
        cmdState = CmdState.DoMangaSequenceCmd()
        cmdState.count = count
        cmdState.dithers = dithers
        cmdState.ditherSeq = dithers*count
        masterThread.do_manga_sequence(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,True)
        self.assertTrue(self.cmd.finished)
    def test_do_manga_sequence(self):
        """
        decenter on,
        count*nDithers*(new dither, expose, readout),
        count*(guider off, ffs closed, ne on, hgcd on, ff off),
        count*(ne on, hgcd on),
        count*(boss expose, readout),
        (count-1)*(ffs open, ne off, hgcd off, ff off, guider on, new dither),
        decenter off, ne off, hgcd off, ff off
        """
        # TBD": Note: until multiCmds are smarter about whether we have to run
        # non-preconditions, things like wht.off will always be sent as part of
        # prepping for things, even though they aren't necessary.
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        count = 3
        dithers = 'NSE'
        self._do_manga_sequence(1 +
                                count*len(dithers)*3 +
                                count*5 + count*2 + count*2 +
                                (count-1)*6 + 4, 151,0,0,count,dithers)
    def test_do_manga_sequence_one_set(self):
        """
        decenter on,
        count*nDithers*(new dither, expose, readout),
        count*(guider off, ffs closed, ne on, hgcd on, ff off),
        count*(ne on, hgcd on),
        count*(boss expose, readout),
        (count-1)*(ffs open, ne off, hgcd off, ff off, guider on, new dither),
        decenter off, ne off, hgcd off, ff off
        """
        # TBD": Note: until multiCmds are smarter about whether we have to run
        # non-preconditions, things like wht.off will always be sent as part of
        # prepping for things, even though they aren't necessary.
        sopTester.updateModel('mcp',TestHelper.mcpState['boss_science'])
        count = 1
        dithers = 'NSE'
        self._do_manga_sequence(1 +
                                count*len(dithers)*3 +
                                count*5 + count*2 + count*2 +
                                (count-1)*6 + 4, 57,0,0,count,dithers)


class TestBossCalibs(MasterThreadTester):
    """do_boss_calibs tests"""
    def _do_boss_calibs(self, nCall, nInfo, nWarn, nErr, cmdState, didFail=False):
        masterThread.do_boss_calibs(self.cmd, cmdState, myGlobals.actorState)
        self._check_cmd(nCall,nInfo,nWarn,nErr,True,didFail=didFail)
    
    def test_do_boss_calibs_one_bias(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nBias = 1
        self._do_boss_calibs(4,13,0,0,cmdState)
    def test_do_boss_calibs_two_bias(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nBias = 2
        self._do_boss_calibs(5,18,0,0,cmdState)

    def test_do_boss_calibs_one_dark(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nDark = 1
        self._do_boss_calibs(4,13,0,0,cmdState)
    def test_do_boss_calibs_two_dark(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nDark = 2
        self._do_boss_calibs(5,18,0,0,cmdState)

    def test_do_boss_calibs_one_flat(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nFlat = 1
        self._do_boss_calibs(7,19,0,0,cmdState)
    def test_do_boss_calibs_two_flat(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nFlat = 2
        self._do_boss_calibs(13,30,0,0,cmdState)
    def test_do_boss_calibs_one_flat_coobserve(self):
        """coobserving carts should close the apogee shutter first."""
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nFlat = 1
        sopTester.updateModel('guider',TestHelper.guiderState['apogeemangaLoaded'])
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_parked'])
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        self._do_boss_calibs(8,26,0,0,cmdState)

    def test_do_boss_calibs_one_arc(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nArc = 1
        self._do_boss_calibs(7,20,0,0,cmdState)
    def test_do_boss_calibs_two_arc(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nArc = 2
        self._do_boss_calibs(12,29,0,0,cmdState)
    def test_do_boss_calibs_one_arc_coobserve(self):
        """coobserving carts should close the apogee shutter first."""
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nArc = 1
        sopTester.updateModel('guider',TestHelper.guiderState['apogeemangaLoaded'])
        sopTester.updateModel('mcp',TestHelper.mcpState['apogee_parked'])
        sopTester.updateModel('apogee',TestHelper.apogeeState['B_open'])
        self._do_boss_calibs(8,27,0,0,cmdState)

    def test_do_boss_calibs_one_of_each(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nBias = 1
        cmdState.nDark = 1
        cmdState.nFlat = 1
        cmdState.nArc = 1
        self._do_boss_calibs(16,43,0,0,cmdState)
    def test_do_boss_calibs_two_of_each(self):
        cmdState = CmdState.DoBossCalibsCmd()
        cmdState.nBias = 2
        cmdState.nDark = 2
        cmdState.nFlat = 2
        cmdState.nArc = 2
        self._do_boss_calibs(29,73,0,0,cmdState)

    def test_do_boss_calibs_flat_arc_fail_on_hgcd(self):
        cmdState = CmdState.DoBossCalibsCmd()
        self.cmd.failOn = "mcp hgcd.on"
        cmdState.nFlat = 1
        cmdState.nArc = 1
        self._do_boss_calibs(7,18,0,1,cmdState,didFail=True)
    def test_do_boss_calibs_two_flat_fail_on_readout(self):
        cmdState = CmdState.DoBossCalibsCmd()
        self.cmd.failOn = "boss exposure   readout"
        cmdState.nFlat = 2
        self._do_boss_calibs(7,18,0,1,cmdState,didFail=True)
    def test_do_boss_calibs_two_arc_fail_on_second_exposure(self):
        cmdState = CmdState.DoBossCalibsCmd()
        self.cmd.failOn = "boss exposure arc itime=4 noreadout"
        self.cmd.failOnCount = 2
        cmdState.nArc = 2
        self._do_boss_calibs(9,28,0,3,cmdState,didFail=True)


if __name__ == '__main__':
    verbosity = 1
    if verbose:
        verbosity = 2
    
    suite = None
    # to test just one piece
    #suite = unittest.TestLoader().loadTestsFromTestCase(TestGuider)
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestGotoField)
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestGotoGangChange)
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestApogeeDomeFlat)
    #suite = unittest.TestLoader().loadTestsFromTestCase(TestApogeeScience)
    #suite = unittest.TestLoader().loadTestsFromTestCase(TestBossScience)
    #suite = unittest.TestLoader().loadTestsFromTestCase(TestHartmann)
    #suite = unittest.TestLoader().loadTestsFromTestCase(TestMangaScience)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBossCalibs)
    # suite = unittest.TestLoader().loadTestsFromName('test_masterThread.TestGotoField.test_goto_field_boss_ffs_open_fails')
    suite = unittest.TestLoader().loadTestsFromName('test_masterThread.TestBossCalibs.test_do_boss_calibs_one_arc_coobserve')
    if suite:
        unittest.TextTestRunner(verbosity=verbosity).run(suite)
    else:
        unittest.main(verbosity=verbosity)
