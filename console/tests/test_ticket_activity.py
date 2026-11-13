import unittest
from types import SimpleNamespace
from unittest import mock

from test_project_model_views import server


class TicketActivityTests(unittest.TestCase):
    def setUp(self):
        self.day = 86400000
        self.now = 30 * self.day + 1234
        self.records = [
            {"id":"goal", "kind":"goal", "parent_status":"ROOT", "parent":None},
            {"id":"task", "kind":"task", "parent_status":"BOUND", "parent":{"id":"goal"}},
        ]
        self.ref = {"membership":"REQUIRED", "manifest_current":True, "task_id":"run", "block_id":"block"}
        self.outcome = {"kind":"ACCEPTED", "timestamp_status":"ORDERED", "observed_at_ms":self.now-100,
                        "task_id":"run", "block_id":"block", "event_id":"event", "linkage":{"state":"LINKED"}}
        self.projection = {"task_manifests":{"run":{"active_version":1,"versions":{1:{"ctrl_id":"ctrl"}}}}}
        self.metadata = {"projects":{"project":{"event_seq":1,"observed_at_ms":23*self.day}}, "receipts":{"event":{}}}
        self.ledger = SimpleNamespace(
            _velocity_read_snapshot=lambda project:(self.projection,[],self.metadata,None,{}),
            ticket_execution_status=lambda projection,project,identity:{"references":[self.ref] if identity=='task' else []},
            project_accepted_progress_rate=lambda *a,**k:{"outcomes":[self.outcome,self.outcome],"reasons":[]},
            _is_non_material_record=lambda item:False)
        self.app = SimpleNamespace(_saved_project_binding=lambda project:{"project_id":"project","root":"C:/tmp", "identities":frozenset({'project'}),"identity_error":None,"native_id":None}, progress_ledger=self.ledger)
        self.read = mock.patch.object(server,'read_project_tickets',return_value={"records":self.records})
        self.read.start();self.addCleanup(self.read.stop)
        self.clock = mock.patch.object(server.time,'time',return_value=self.now/1000)
        self.clock.start();self.addCleanup(self.clock.stop)

    def request(self,operation):
        return server.App.project_ticket_command(self.app,{"operation":operation,"project_id":"project","record_id":"goal"})

    def test_activity_deduplicates_and_preserves_unknown_coverage(self):
        result=self.request('read_activity')
        self.assertEqual(len(result['days']),7)
        self.assertEqual(result['days'][-1]['accepted'],1)
        self.ref['manifest_current']=False
        self.assertTrue(all(day['accepted'] is None for day in self.request('read_activity')['days']))
        self.ref['manifest_current']=True
        self.metadata['projects']['project']['observed_at_ms']=self.now
        self.assertTrue(all(day['accepted'] is None for day in self.request('read_activity')['days']))

    def test_unbound_child_blocks_make_parent_activity_unknown(self):
        self.records.extend([
            {"id":"child-a", "kind":"block", "parent_status":"BOUND", "parent":{"id":"task"}},
            {"id":"child-b", "kind":"block", "parent_status":"BOUND", "parent":{"id":"task"}},
        ])
        self.assertTrue(all(day['accepted'] is None for day in self.request('read_activity')['days']))

    def test_selected_bound_block_has_its_own_activity(self):
        self.records.append({"id":"child", "kind":"block", "parent_status":"BOUND", "parent":{"id":"task"}})
        self.ledger.ticket_execution_status=lambda projection,project,identity:{"references":[self.ref] if identity=='child' else []}
        result=server.App.project_ticket_command(self.app,{"operation":"read_activity","project_id":"project","record_id":"child"})
        self.assertEqual(result['days'][-1]['accepted'],1)

    def test_logs_filter_sibling_blocks_and_keep_unknown_model(self):
        event=lambda block,event_id:{"event_id":event_id,"event_seq":1,"task_id":"run","action_target":{"subject_id":block}}
        self.app.run_log=lambda *a,**k:{"items":[event('block','own'),event('other','sibling')],"retention":{"page_truncated":False,"source_scan_truncated":False}}
        result=self.request('read_logs')
        self.assertEqual([x['event_id'] for x in result['items']],['own'])
        self.assertNotIn('model',result['items'][0])


if __name__=='__main__': unittest.main()
