"""
Test creating and destroying CmdStates.
"""

import unittest

import sopActor
import sopActor.myGlobals as myGlobals

from actorcore import TestHelper
import sopTester

class TestKeywords(sopTester.SopTester,unittest.TestCase):
    def setUp(self):
        self.userKeys = False
        self.verbose = True
        self.ok_stage = ''
        self.ok_state = 'done'
        self.stages = ['1','2']
        self.keywords = {'a':1,'b':2}
        self.cmdState = sopActor.CmdState.CmdState('tester',self.stages,keywords=self.keywords)
        super(TestKeywords,self).setUp()
        
    def test_reset_keywords(self):
        self.cmdState.a = 100
        self.cmdState.b = 200
        self.cmdState.reset_keywords()
        for n in self.keywords:
            self.assertEquals(getattr(self.cmdState,n),self.keywords[n])
    
    def test_reinitialize(self):
        self.cmdState.setStageState('1','running')
        self.cmdState.setStageState('2','aborted')
        self.cmdState.reinitialize()
        for n in self.stages:
            self.assertEquals(self.cmdState.stages[n],'idle')
    
    def test_set_item_ok(self):
        x = 1000
        self.cmdState.set('a',x)
        self.assertEqual(self.cmdState.a,x)
    def test_set_item_invalid(self):
        with self.assertRaises(AssertionError):
            self.cmdState.set('not_valid',-1)
    def test_set_item_default(self):
        self.cmdState.set('a',None)
        self.assertEqual(self.cmdState.a,self.cmdState.keywords['a'])


class CmdStateTester(sopTester.SopTester):
    def setUp(self):
        self.userKeys = False
        self.verbose = True
        self.ok_stage = ''
        self.ok_state = 'done'
        super(CmdStateTester,self).setUp()
    
    def test_setStageState_ok(self):
        """Valid stage states output one msg: State"""
        stage = self.ok_stage
        state = self.ok_state
        self.cmdState.setStageState(stage,state)
        self.assertEqual(self.cmdState.stages[stage],state)
        self.assertEqual(self.cmd.levels.count('i'),1)
    
    def test_setStageState_badStage(self):
        with self.assertRaises(AssertionError):
            self.cmdState.setStageState('not_a_state!',self.ok_state)
    def test_setStageState_badState(self):
        with self.assertRaises(AssertionError):
            self.cmdState.setStageState(self.ok_stage,'bad')
    
    def test_setCommandState_running(self):
        """
        setCommandState outputs 3 or 4 inform level commands:
        Stages, State, StateKeys [UserKeys].
        """
        inform = 3 + (1 if self.userKeys else 0)
        state = 'running'
        self.cmdState.setCommandState(state)
        self.assertEqual(self.cmdState.cmdState,state)
        self.assertEqual(self.cmd.levels.count('i'),inform)
        self.assertEqual(self.cmd.levels.count('w'),0)
    def test_setCommandState_failed(self):
        inform = 3 + (1 if self.userKeys else 0)
        state = 'failed'
        stateText = 'I failed!'
        self.cmdState.setCommandState(state,stateText=stateText)
        self.assertEqual(self.cmdState.cmdState,state)
        self.assertEqual(self.cmdState.stateText,stateText)
        self.assertEqual(self.cmd.levels.count('i'),inform)
        self.assertEqual(self.cmd.levels.count('w'),0)
    
    def test_isSlewingDisabled_BOSS_integrating(self):
        sopTester.updateModel('boss',TestHelper.bossState['integrating'])
        result = self.cmdState.isSlewingDisabled_BOSS()
        self.assertEqual(result,'INTEGRATING')
    def test_isSlewingDisabled_BOSS_no(self):
        sopTester.updateModel('boss',TestHelper.bossState['reading'])
        result = self.cmdState.isSlewingDisabled_BOSS()
        self.assertFalse(result)
    
    def _isSlewingDisabled_because_exposing(self, survey, nExp, state):
        self.cmdState.cmd = self.cmd
        result = self.cmdState.isSlewingDisabled()
        self.assertIsInstance(result,str)
        self.assertIn('slewing disallowed for %s'%survey,result)
        self.assertIn('with %d science exposure %s'%(nExp,state),result)
    
    def _isSlewingDisabled_no_cmd(self):
        self.cmdState.cmd = None
        result = self.cmdState.isSlewingDisabled()
        self.assertFalse(result)
    def _isSlewingDisabled_cmd_finished(self):
        self.cmdState.cmd = self.cmd
        self.cmdState.finished = True
        result = self.cmdState.isSlewingDisabled()
        self.assertFalse(result)


class TestGotoGangChange(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestGotoGangChange,self).setUp()
        self.cmdState = sopActor.CmdState.GotoGangChangeCmd()
        self.ok_stage = 'slew'

class TestGotoField(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestGotoField,self).setUp()
        self.cmdState = sopActor.CmdState.GotoFieldCmd()
        self.ok_stage = 'slew'

class TestDoBossCalibs(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoBossCalibs,self).setUp()
        self.cmdState = sopActor.CmdState.DoBossCalibsCmd()
        self.userKeys = True
        self.ok_stage = 'flat'

class TestDoApogeeScience(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoApogeeScience,self).setUp()
        self.cmdState = sopActor.CmdState.DoApogeeScienceCmd()
        self.userKeys = True
        self.ok_stage = 'expose'

class TestDoApogeeSkyFlats(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoApogeeSkyFlats,self).setUp()
        self.cmdState = sopActor.CmdState.DoApogeeSkyFlatsCmd()
        self.ok_stage = 'expose'

class TestDoApogeeDomeFlat(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoApogeeDomeFlat,self).setUp()
        self.cmdState = sopActor.CmdState.DoApogeeDomeFlatCmd()
        self.ok_stage = 'domeFlat'

class TestDoBossScience(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoBossScience,self).setUp()
        self.cmdState = sopActor.CmdState.DoBossScienceCmd()
        self.ok_stage = 'expose'
        self.userKeys = True

class TestDoMangaSequence(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoMangaSequence,self).setUp()
        self.cmdState = sopActor.CmdState.DoMangaSequenceCmd()
        self.ok_stage = 'dither'
        self.userKeys = True

    def test_isSlewingDisabled_no_cmd(self):
        result = self.cmdState.isSlewingDisabled()
        self.cmdState.cmd = None
        self.assertFalse(result)



class TestDoMangaDither(CmdStateTester,unittest.TestCase):
    def setUp(self):
        super(TestDoMangaDither,self).setUp()
        self.cmdState = sopActor.CmdState.DoMangaDitherCmd()
        self.ok_stage = 'dither'
    
    def test_isSlewingDisabled_because_exposing(self):
        sopTester.updateModel('boss',TestHelper.bossState['integrating'])
        self._isSlewingDisabled_because_exposing('MaNGA',1,'INTEGRATING')
    
    def test_isSlewingDisabled_no(self):
        sopTester.updateModel('boss',TestHelper.bossState['reading'])
        self.cmdState.cmd = self.cmd
        result = self.cmdState.isSlewingDisabled()
        self.assertFalse(result)


if __name__ == '__main__':
    verbosity = 2
    
    unittest.main(verbosity=verbosity)


