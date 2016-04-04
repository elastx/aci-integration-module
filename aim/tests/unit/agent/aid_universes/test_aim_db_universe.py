# Copyright (c) 2016 Cisco Systems
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock

from aim.agent.aid.universes import aim_universe
from aim.common.hashtree import structured_tree as tree
from aim.db import agent_model  # noqa
from aim.db import tree_model
from aim.tests import base


class TestAimDbUniverse(base.TestAimDBBase):

    def setUp(self):
        super(TestAimDbUniverse, self).setUp()
        self.universe = aim_universe.AimDbUniverse().initialize(self.session)
        self.tree_mgr = tree_model.TREE_MANAGER

    def test_serve(self):
        # Serve the first batch of tenants
        tenants = ['tn%s' % x for x in range(10)]
        self.universe.serve(tenants)
        self.assertEqual(set(tenants), set(self.universe._served_tenants))

    def test_state(self):
        # Create some trees in the AIM DB
        data1 = tree.StructuredHashTree().include(
            [{'key': ('tnA', 'keyB')}, {'key': ('tnA', 'keyC')},
             {'key': ('tnA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('tnA1', 'keyB')}, {'key': ('tnA1', 'keyC')},
             {'key': ('tnA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('tnA2', 'keyB')}, {'key': ('tnA2', 'keyC')},
             {'key': ('tnA2', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data1, data2, data3])
        # Serve tnA, tnA2 and tnExtra
        self.universe.serve(['tnA', 'tnA2', 'tnExtra'])
        # Now observe
        state = self.universe.state
        # tnA and tnA2 have updated values, tnExtra is still empty
        self.assertEqual(data1, state['tnA'])
        self.assertEqual(data3, state['tnA2'])
        self.assertIsNone(state.get('tnExtra'))

        # Change tree in the DB
        data1.add(('tnA', 'keyB'), attribute='something')
        self.tree_mgr.update_bulk(self.ctx, [data1])
        # Observe and verify that trees are back in sync
        self.assertNotEqual(data1, state['tnA'])
        state = self.universe.state
        self.assertEqual(data1, state['tnA'])

    def test_reconcile_raises(self):
        self.assertRaises(NotImplementedError, self.universe.reconcile,
                          mock.Mock())

    def test_get_optimized_state(self):
        data1 = tree.StructuredHashTree().include(
            [{'key': ('tnA', 'keyB')}, {'key': ('tnA', 'keyC')},
             {'key': ('tnA', 'keyC', 'keyD')}])
        data2 = tree.StructuredHashTree().include(
            [{'key': ('tnA1', 'keyB')}, {'key': ('tnA1', 'keyC')},
             {'key': ('tnA1', 'keyC', 'keyD')}])
        data3 = tree.StructuredHashTree().include(
            [{'key': ('tnA2', 'keyB')}, {'key': ('tnA2', 'keyC')},
             {'key': ('tnA2', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data1, data2, data3])

        self.universe.serve(['tnA', 'tnA1', 'tnA2', 'tnA3'])
        # Other state is in sync
        other_state = {
            'tnA': tree.StructuredHashTree().from_string(str(data1)),
            'tnA1': tree.StructuredHashTree().from_string(str(data2)),
            'tnA2': tree.StructuredHashTree().from_string(str(data3))}
        # Optimized state is empty
        self.assertEqual({}, self.universe.get_optimized_state(other_state))

        # Add a new tenant
        data4 = tree.StructuredHashTree().include(
            [{'key': ('tnA3', 'keyB')}, {'key': ('tnA3', 'keyC')},
             {'key': ('tnA3', 'keyC', 'keyD')}])
        self.tree_mgr.update_bulk(self.ctx, [data4])
        self.assertEqual({'tnA3': data4},
                         self.universe.get_optimized_state(other_state))
        # Modify data1
        data1.add(('tnA', 'keyZ'), attribute='something')
        self.tree_mgr.update_bulk(self.ctx, [data1])
        # Now Data1 is included too
        self.assertEqual({'tnA3': data4, 'tnA': data1},
                         self.universe.get_optimized_state(other_state))
