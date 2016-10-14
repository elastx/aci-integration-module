# Copyright (c) 2016 Cisco Systems
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import abc
import six

from oslo_log import log as logging

from aim.aim_lib.db import model
from aim.api import resource
from aim import utils as aim_utils

LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class NatStrategy(object):
    """Interface for NAT behavior strategies.

    Defines interface for configuring L3Outside in AIM to support
    various kinds of NAT-ing.
    All methods expect AIM resources as input parameters.

    Example usage:

    1. Decide a NAT-strategy to use

    mgr = AimManager()
    ctx = AimContext()
    ns = DistributedNatStrategy(mgr)     # or NoNatEdgeStrategy(mgr),
                                         # or EdgeNatStrategy(mgr)

    2. Create L3Outside and one or more ExternalNetworks. Subnets
    may be created in the L3Outside

    l3out = L3Outside(tenant_name='t1', name='out')
    ext_net1 = ExternalNetwork(tenant_name='t1', l3out_name='out',
                               name='inet1')
    ext_net2 = ExternalNetwork(tenant_name='t1', l3out_name='out',
                               name='inet2')

    ns.create_l3outside(ctx, l3out)
    ns.create_subnet(ctx, l3out, '40.40.40.1/24')
    ns.create_external_network(ctx, ext_net1)
    ns.create_external_network(ctx, ext_net2)

    3. Allow traffic for certain IP-addresses through the external
       networks; by default no traffic is allowed.

    ns.update_external_cidrs(ctx, ext_net1, ['0.0.0.0/0'])
    ns.update_external_cidrs(ctx, ext_net2, ['200.200.0.0/16',
                                             '300.0.0.0/8'])

    3. To provide external-connectivity to a VRF, connect the VRF to
    ExternalNetwork with appropriate contracts.

    ext_net1.provided_contract_names = ['http', 'icmp']
    ext_net1.consumed_contract_names = ['arp']

    vrf = VRF(...)

    ns.connect_vrf(ctx, ext_net1, vrf)

    4. Call connect_vrf() again to update the contracts

    ext_net1.provided_contract_names = ['http', 'https']
    ext_net1.consumed_contract_names = ['ping']

    ns.connect_vrf(ctx, ext_net1, vrf)

    5. Disallow external-connectivity to VRF

    ns.disconnect_vrf(ctx, ext_net1, vrf)

    6. Delete ExternalNetwork, subnet and L3Outside

    ns.delete_external_network(ctx, ext_net1)
    ns.delete_external_network(ctx, ext_net2)
    ns.delete_subnet(ctx, l3out, '40.40.40.1/24')
    ns.delete_l3outside(ctx, l3out)

    """

    @abc.abstractmethod
    def create_l3outside(self, ctx, l3outside):
        """Create L3Outside object if needed.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :return: L3Outside resource
        """

    @abc.abstractmethod
    def delete_l3outside(self, ctx, l3outside):
        """Delete L3Outside object.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :return:
        """

    @abc.abstractmethod
    def get_l3outside_resources(self, ctx, l3outside):
        """Get AIM resources that are created for an L3Outside object.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :return: List of AIm resources
        """

    @abc.abstractmethod
    def create_subnet(self, ctx, l3outside, gw_ip_mask):
        """Create Subnet in L3Outside.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of subnet to create
        :return:
        """

    @abc.abstractmethod
    def delete_subnet(self, ctx, l3outside, gw_ip_mask):
        """Delete Subnet in L3Outside.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of subnet to delete
        :return:
        """

    @abc.abstractmethod
    def get_subnet(self, ctx, l3outside, gw_ip_mask):
        """Get Subnet in L3Outside with specified Gateway+CIDR.

        :param ctx: AIM context
        :param l3outside: L3Outside AIM resource
        :param gw_ip_mask: Gateway+CIDR of subnet to fetch
        :return: AIM Subnet if one is found
        """

    @abc.abstractmethod
    def create_external_network(self, ctx, external_network):
        """Create ExternalNetwork object if needed.

        :param ctx: AIM context
        :param external_network: ExternalNetwork AIM resource
        :return: ExternalNetwork resource
        """

    @abc.abstractmethod
    def delete_external_network(self, ctx, external_network):
        """Delete ExternalNetwork object.

        :param ctx: AIM context
        :param external_network: ExternalNetwork AIM resource
        :return:
        """

    @abc.abstractmethod
    def update_external_cidrs(self, ctx, external_network, external_cidrs):
        """Set the IP addresses for which external traffic is allowed.

        :param ctx: AIM context
        :param external_network: ExternalNetwork AIM resource
        :param external_cidrs: List of CIDRs to allow
        :return:
        """

    @abc.abstractmethod
    def connect_vrf(self, ctx, external_network, vrf):
        """Allow external connectivity to VRF.

        Create or update NAT machinery to allow external
        connectivity from a given VRF to an ExternalNetwork (L3Outside)
        enforcing the policies specified in ExternalNetwork.

        :param ctx: AIM context
        :param external_network: AIM ExternalNetwork
        :param vrf: AIM VRF
        :return:
        """

    @abc.abstractmethod
    def disconnect_vrf(self, ctx, external_network, vrf):
        """Remove external connectivity for VRF.

        Tear down connectivity between VRF and ExternalNetwork (L3Outside).

        :param ctx: AIM context
        :param external_network: AIM ExternalNetwork
        :param vrf: AIM VRF
        """


class NatStrategyMixin(NatStrategy):
    """Implements common functionality between different NAT strategies."""

    def __init__(self, mgr):
        self.mgr = mgr
        self.db = model.CloneL3OutManager()

    def create_l3outside(self, ctx, l3outside):
        return self._create_l3out(ctx, l3outside)

    def delete_l3outside(self, ctx, l3outside):
        self._delete_l3out(ctx, l3outside)

    def get_l3outside_resources(self, ctx, l3outside):
        res = []
        l3out = self.mgr.get(ctx, l3outside)
        if l3out:
            res.append(l3out)
            for obj in self._get_nat_objects(ctx, l3out):
                obj_db = self.mgr.get(ctx, obj)
                if obj_db:
                    res.append(obj_db)
        return res

    def create_external_network(self, ctx, external_network):
        return self._create_ext_net(ctx, external_network)

    def delete_external_network(self, ctx, external_network):
        self._delete_ext_net(ctx, external_network)

    def create_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            nat_bd = self._get_nat_bd(ctx, l3outside)
            sub = resource.Subnet(tenant_name=nat_bd.tenant_name,
                                  bd_name=nat_bd.name,
                                  gw_ip_mask=gw_ip_mask)
            if not self.mgr.get(ctx, sub):
                self.mgr.create(ctx, sub)

    def delete_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            nat_bd = self._get_nat_bd(ctx, l3outside)
            sub = resource.Subnet(tenant_name=nat_bd.tenant_name,
                                  bd_name=nat_bd.name,
                                  gw_ip_mask=gw_ip_mask)
            self.mgr.delete(ctx, sub)

    def get_subnet(self, ctx, l3outside, gw_ip_mask):
        l3outside = self.mgr.get(ctx, l3outside)
        if l3outside:
            nat_bd = self._get_nat_bd(ctx, l3outside)
            sub = resource.Subnet(tenant_name=nat_bd.tenant_name,
                                  bd_name=nat_bd.name,
                                  gw_ip_mask=gw_ip_mask)
            return self.mgr.get(ctx, sub)

    def update_external_cidrs(self, ctx, external_network, external_cidrs):
        ext_net_db = self.mgr.get(ctx, external_network)
        if ext_net_db:
            self._manage_external_subnets(ctx, ext_net_db, external_cidrs)

    def _create_l3out(self, ctx, l3out):
        """Create NAT EPG etc. in addition to creating L3Out."""

        with ctx.db_session.begin(subtransactions=True):
            l3out_db = self.mgr.get(ctx, l3out)
            if not l3out_db:
                l3out_db = self.mgr.create(ctx, l3out)
            self._create_nat_epg(ctx, l3out_db)
            ext_vrf = self._get_nat_vrf(ctx, l3out_db)
            l3out_db = self.mgr.update(ctx, l3out_db,
                                       vrf_name=ext_vrf.name)
            return l3out_db

    def _delete_l3out(self, ctx, l3out, delete_epg=True):
        """Delete NAT EPG etc. in addition to deleting L3Out."""

        with ctx.db_session.begin(subtransactions=True):
            l3out_db = self.mgr.get(ctx, l3out)
            if l3out_db:
                for en in self.mgr.find(ctx, resource.ExternalNetwork,
                                        tenant_name=l3out.tenant_name,
                                        l3out_name=l3out.name):
                    self.delete_external_network(ctx, en)
                if not l3out_db.monitored:
                    self.mgr.delete(ctx, l3out)
                else:
                    self.mgr.update(ctx, l3out, vrf_name='')
                if delete_epg:
                    self._delete_nat_epg(ctx, l3out_db)

    def _create_ext_net(self, ctx, ext_net):
        with ctx.db_session.begin(subtransactions=True):
            ext_net_db = self.mgr.get(ctx, ext_net)
            if not ext_net_db:
                ext_net_db = self.mgr.create(ctx, ext_net)
            l3out = self.mgr.get(ctx,
                                 self._ext_net_to_l3out(ext_net))
            contract = self._get_nat_contract(ctx, l3out)
            ext_net_db = self._update_contract(ctx, ext_net_db, contract,
                                               is_remove=False)
            return ext_net_db

    def _delete_ext_net(self, ctx, ext_net):
        with ctx.db_session.begin(subtransactions=True):
            ext_net_db = self.mgr.get(ctx, ext_net)
            if ext_net_db:
                self._manage_external_subnets(ctx, ext_net_db, [])
                if not ext_net_db.monitored:
                    self.mgr.delete(ctx, ext_net)
                else:
                    l3out = self.mgr.get(
                        ctx, self._ext_net_to_l3out(ext_net))
                    contract = self._get_nat_contract(ctx, l3out)
                    self._update_contract(ctx, ext_net_db, contract,
                                          is_remove=True)

    def _set_bd_l3out(self, ctx, l3outside, vrf):
        # update all the BDs
        for bd in self.mgr.find(ctx, resource.BridgeDomain,
                                tenant_name=vrf.tenant_name,
                                vrf_name=vrf.name):
            # Add L3Out to existing list
            self.mgr.update(ctx, bd,
                            l3out_names=bd.l3out_names + [l3outside.name])
        # TODO(ivar): if the VRF is in common tenant, then great pain
        # awaits, since any BD in the system could be pointing to it
        # if no local reference exists.

    def _unset_bd_l3out(self, ctx, l3outside, vrf):
        # update all the BDs
        for bd in self.mgr.find(ctx, resource.BridgeDomain,
                                tenant_name=vrf.tenant_name,
                                vrf_name=vrf.name):
            # Remove L3Out from existing list
            if l3outside.name in bd.l3out_names:
                bd.l3out_names.remove(l3outside.name)
            self.mgr.update(ctx, bd, l3out_names=bd.l3out_names)
        # TODO(ivar): if the VRF is in common tenant, then great pain
        # awaits, since any BD in the system could be pointing to it
        # if no local reference exists.

    def _manage_external_subnets(self, ctx, ext_net, new_cidrs):
        new_cidrs = new_cidrs[:] if new_cidrs else []
        ext_sub_attr = dict(tenant_name=ext_net.tenant_name,
                            l3out_name=ext_net.l3out_name,
                            external_network_name=ext_net.name)
        old_ext_subs = self.mgr.find(ctx, resource.ExternalSubnet,
                                     **ext_sub_attr)
        with ctx.db_session.begin(subtransactions=True):
            for sub in old_ext_subs:
                if sub.cidr in new_cidrs:
                    new_cidrs.remove(sub.cidr)
                else:
                    self.mgr.delete(ctx, sub)
            for c in new_cidrs:
                self.mgr.create(ctx, resource.ExternalSubnet(cidr=c,
                                                             **ext_sub_attr))

    def _ext_net_to_l3out(self, ext_net):
        return resource.L3Outside(tenant_name=ext_net.tenant_name,
                                  name=ext_net.l3out_name)

    def _display_name(self, res):
        return (getattr(res, 'display_name', None) or res.name)

    def _get_nat_ap_epg(self, ctx, l3out):
        d_name = self._display_name(l3out)
        ap_name = getattr(self, 'app_profile_name', None) or l3out.name
        ap_display_name = aim_utils.sanitize_display_name(
            getattr(self, 'app_profile_name', None) or d_name)
        ap = resource.ApplicationProfile(
            tenant_name=l3out.tenant_name,
            name=ap_name,
            display_name=ap_display_name)
        epg = resource.EndpointGroup(
            tenant_name=ap.tenant_name,
            app_profile_name=ap.name,
            name='EXT-%s' % l3out.name,
            display_name=aim_utils.sanitize_display_name('EXT-%s' % d_name))
        return (ap, epg)

    def _get_nat_contract(self, ctx, l3out):
        d_name = self._display_name(l3out)
        return resource.Contract(
            tenant_name=l3out.tenant_name,
            name='EXT-%s' % l3out.name,
            display_name=aim_utils.sanitize_display_name('EXT-%s' % d_name))

    def _get_nat_bd(self, ctx, l3out):
        d_name = self._display_name(l3out)
        return resource.BridgeDomain(
            tenant_name=l3out.tenant_name,
            name='EXT-%s' % l3out.name,
            display_name=aim_utils.sanitize_display_name('EXT-%s' % d_name),
            l3out_names=[l3out.name])

    def _get_nat_vrf(self, ctx, l3out):
        d_name = self._display_name(l3out)
        return resource.VRF(
            tenant_name=l3out.tenant_name,
            name='EXT-%s' % l3out.name,
            display_name=aim_utils.sanitize_display_name('EXT-%s' % d_name))

    def _get_nat_objects(self, ctx, l3out):
        sani = aim_utils.sanitize_display_name
        d_name = self._display_name(l3out)
        fltr = resource.Filter(
            tenant_name=l3out.tenant_name,
            name='EXT-%s' % l3out.name,
            display_name=sani('EXT-%s' % d_name))
        entry = resource.FilterEntry(
            tenant_name=fltr.tenant_name,
            filter_name=fltr.name,
            name='Any',
            display_name='Any')
        contract = self._get_nat_contract(ctx, l3out)
        subject = resource.ContractSubject(
            tenant_name=contract.tenant_name,
            contract_name=contract.name,
            name='Allow', display_name='Allow',
            bi_filters=[fltr.name])
        vrf = self._get_nat_vrf(ctx, l3out)
        bd = self._get_nat_bd(ctx, l3out)
        bd.vrf_name = vrf.name
        ap, epg = self._get_nat_ap_epg(ctx, l3out)
        vm_doms = getattr(
            self, 'vmm_domain_names',
            [d.name for d in self.mgr.find(ctx, resource.VMMDomain)])
        phy_doms = getattr(
            self, 'physical_domain_names',
            [d.name for d in self.mgr.find(ctx, resource.PhysicalDomain)])
        epg.bd_name = bd.name
        epg.provided_contract_names = [contract.name]
        epg.consumed_contract_names = [contract.name]
        epg.openstack_vmm_domain_names = vm_doms
        epg.physical_domain_names = phy_doms
        return [fltr, entry, contract, subject, vrf, bd, ap, epg]

    def _create_nat_epg(self, ctx, l3out):
        objs = self._get_nat_objects(ctx, l3out)
        with ctx.db_session.begin(subtransactions=True):
            for r in objs:
                if not self.mgr.get(ctx, r):
                    self.mgr.create(ctx, r)

    def _delete_nat_epg(self, ctx, l3out):
        with ctx.db_session.begin(subtransactions=True):
            nat_bd = self._get_nat_bd(ctx, l3out)
            for sub in self.mgr.find(ctx, resource.Subnet,
                                     tenant_name=nat_bd.tenant_name,
                                     bd_name=nat_bd.name):
                self.mgr.delete(ctx, sub)
            for r in reversed(self._get_nat_objects(ctx, l3out)):
                if isinstance(r, resource.ApplicationProfile):
                    epgs = self.mgr.find(ctx, resource.EndpointGroup,
                                         tenant_name=r.tenant_name,
                                         app_profile_name=r.name)
                    if epgs:
                        continue
                self.mgr.delete(ctx, r)

    def _update_contract(self, ctx, ext_net, contract, is_remove):
        if is_remove:
            prov = [c for c in ext_net.provided_contract_names
                    if c != contract.name]
            cons = [c for c in ext_net.consumed_contract_names
                    if c != contract.name]
        else:
            prov = [contract.name]
            prov.extend(ext_net.provided_contract_names)
            cons = [contract.name]
            cons.extend(ext_net.consumed_contract_names)
        ext_net = self.mgr.update(ctx, ext_net,
                                  provided_contract_names=prov,
                                  consumed_contract_names=cons)
        return ext_net


class NoNatStrategy(NatStrategyMixin):
    """No NAT Strategy.

    Provides direct external connectivity without any network
    address translation.
    """

    def connect_vrf(self, ctx, external_network, vrf):
        """Allow external connectivity to VRF.

        Make external_network provide/consume specified contracts.
        Set vrf_name of L3Outside to VRF.
        Locate BDs referring to the VRF, and include L3Outside
        in their l3out_names.
        """
        with ctx.db_session.begin(subtransactions=True):
            self.mgr.update(
                ctx, external_network,
                **{k: getattr(external_network, k)
                   for k in ['provided_contract_names',
                             'consumed_contract_names']})
            l3outside = self._ext_net_to_l3out(external_network)
            l3outside = self.mgr.update(ctx, l3outside, vrf_name=vrf.name)
            self._set_bd_l3out(ctx, l3outside, vrf)

    def disconnect_vrf(self, ctx, external_network, vrf):
        """Remove external connectivity for VRF.

        Remove contracts provided/consumed by external_network.
        Unset vrf_name of L3Outside.
        Locate BDs referring to the VRF, and exclude L3Outside
        from their l3out_names.
        """
        with ctx.db_session.begin(subtransactions=True):
            l3outside = self.mgr.get(ctx,
                                     self._ext_net_to_l3out(external_network))
            contract = self._get_nat_contract(ctx, l3outside)
            self.mgr.update(ctx, external_network,
                            provided_contract_names=[contract.name],
                            consumed_contract_names=[contract.name])
            nat_vrf = self._get_nat_vrf(ctx, l3outside)
            self.mgr.update(ctx, l3outside,
                            vrf_name=nat_vrf.name)
            self._unset_bd_l3out(ctx, l3outside, vrf)


class DistributedNatStrategy(NatStrategyMixin):
    """Distributed NAT Strategy.

    Provides external connectivity with network address
    translation (DNAT/SNAT) where the translation is distributed
    amongst nodes in the fabric.

    """

    def delete_external_network(self, ctx, external_network):
        """Delete external-network from main and cloned L3Outs.

        """
        with ctx.db_session.begin(subtransactions=True):
            # Delete specified external-network from all cloned L3Outs.
            # Delete external-network from main L3Out.
            l3out = self.mgr.get(ctx,
                                 self._ext_net_to_l3out(external_network))
            ext_net_db = self.mgr.get(ctx, external_network)
            if l3out and ext_net_db:
                clone_l3outs = self._find_l3out_clones(ctx, l3out)
                for clone in clone_l3outs:
                    clone_ext_net = resource.ExternalNetwork(
                        tenant_name=clone.tenant_name,
                        l3out_name=clone.name,
                        name=ext_net_db.name)
                    self._delete_ext_net(ctx, clone_ext_net)
                    self._delete_unused_l3out(ctx, clone)
            self._delete_ext_net(ctx, ext_net_db)

    def update_external_cidrs(self, ctx, external_network, external_cidrs):
        """Update external CIDRs in main and cloned ExternalNetworks."""
        l3out = self.mgr.get(ctx, self._ext_net_to_l3out(external_network))
        ext_net_db = self.mgr.get(ctx, external_network)
        if l3out and ext_net_db:
            clone_l3outs = self._find_l3out_clones(ctx, l3out)
            with ctx.db_session.begin(subtransactions=True):
                for clone in clone_l3outs:
                    clone_ext_net = resource.ExternalNetwork(
                        tenant_name=clone.tenant_name,
                        l3out_name=clone.name,
                        name=external_network.name)
                    self._manage_external_subnets(ctx, clone_ext_net,
                                                  external_cidrs)
                self._manage_external_subnets(ctx, ext_net_db,
                                              external_cidrs)

    def connect_vrf(self, ctx, external_network, vrf):
        """Allow external connectivity to VRF.

        Create shadow L3Outside for L3Outside-VRF combination
        in VRF's tenant, if required.
        Create ExternalNetwork and ExternalSubnet(s) in the shadow
        L3Out, if required.
        Set vrf_name of shadow L3Outside to VRF.

        """
        with ctx.db_session.begin(subtransactions=True):
            return self._create_shadow(ctx, external_network, vrf)

    def disconnect_vrf(self, ctx, external_network, vrf):
        """Remove external connectivity for VRF.

        Delete ExternalNetwork and contained ExternalSubnet
        in the shadow L3Outside. Remove shadow L3Outside if
        there are no more ExternalNetworks in the shadow
        L3Outside.
        """
        with ctx.db_session.begin(subtransactions=True):
            self._delete_shadow(ctx, external_network, vrf)

    def _generate_l3out_name(self, l3outside, vrf):
        # Generate a name based on its relationship with VRF
        name = '%s-%s' % (l3outside.name, vrf.name)
        display_name = aim_utils.sanitize_display_name(
            '%s-%s' % (self._display_name(l3outside),
                       self._display_name(vrf)))
        return (name, display_name)

    def _make_l3out_clone(self, ctx, l3out, vrf):
        new_tenant = vrf.tenant_name
        new_name, new_display_name = self._generate_l3out_name(l3out, vrf)

        clone_l3out = resource.L3Outside(
            tenant_name=new_tenant,
            name=new_name,
            display_name=new_display_name,
            vrf_name=vrf.name)
        return clone_l3out

    def _create_shadow(self, ctx, ext_net, vrf, with_nat_epg=True):
        """Clone ExternalNetwork as a shadow."""

        ext_net_db = self.mgr.get(ctx, ext_net)
        if not ext_net_db:
            return
        l3out = self.mgr.get(ctx, self._ext_net_to_l3out(ext_net_db))
        clone_l3out = self._make_l3out_clone(ctx, l3out, vrf)
        clone_ext_net = resource.ExternalNetwork(
            tenant_name=clone_l3out.tenant_name,
            l3out_name=clone_l3out.name,
            display_name=ext_net_db.display_name,
            **{k: getattr(ext_net, k)
               for k in ['name',
                         'provided_contract_names',
                         'consumed_contract_names']})
        if with_nat_epg:
            _, nat_epg = self._get_nat_ap_epg(ctx, l3out)
            clone_ext_net.nat_epg_dn = nat_epg.dn

        with ctx.db_session.begin(subtransactions=True):
            self.mgr.create(ctx, clone_l3out, overwrite=True)
            self.mgr.create(ctx, clone_ext_net, overwrite=True)
            cidrs = self.mgr.find(ctx, resource.ExternalSubnet,
                                  tenant_name=ext_net_db.tenant_name,
                                  external_network_name=ext_net_db.name)
            cidrs = [c.cidr for c in cidrs]
            self._manage_external_subnets(ctx, clone_ext_net, cidrs)
            # Set this item as a clone
            if not self.db.get(ctx, clone_l3out):
                self.db.set(ctx, l3out, clone_l3out)
            return clone_ext_net

    def _delete_shadow(self, ctx, ext_net, vrf):
        l3out = self.mgr.get(ctx, self._ext_net_to_l3out(ext_net))

        clone_l3out = resource.L3Outside(
            tenant_name=vrf.tenant_name,
            name=self._generate_l3out_name(l3out, vrf)[0])
        clone_ext_net = resource.ExternalNetwork(
            tenant_name=clone_l3out.tenant_name,
            l3out_name=clone_l3out.name,
            name=ext_net.name)

        with ctx.db_session.begin(subtransactions=True):
            self._delete_ext_net(ctx, clone_ext_net)
            self._delete_unused_l3out(ctx, clone_l3out)

    def _find_l3out_clones(self, ctx, l3outside):
        clone_keys = self.db.get_clones(ctx, l3outside)
        return [resource.L3Outside(tenant_name=x[0], name=x[1])
                for x in clone_keys]

    def _delete_unused_l3out(self, ctx, l3out):
        ens = self.mgr.find(ctx, resource.ExternalNetwork,
                            tenant_name=l3out.tenant_name,
                            l3out_name=l3out.name)
        if not ens:
            self._delete_l3out(ctx, l3out)


class EdgeNatStrategy(DistributedNatStrategy):
    """Edge NAT Strategy.

    Provides external connectivity with network address
    translation (DNAT/SNAT) where the translation is centralized
    in a node at the edge of the fabric.
    """

    def connect_vrf(self, ctx, external_network, vrf, external_cidrs=None):
        """Allow external connectivity to VRF.

        Create shadow L3Outside for L3Outside-VRF combination
        in VRF's tenant, if required.
        Create ExternalNetwork and ExternalSubnet in the shadow
        L3Out, if required.
        Set vrf_name of shadow L3Outside to VRF.

        """
        with ctx.db_session.begin(subtransactions=True):
            return self._create_shadow(ctx, external_network, vrf,
                                       with_nat_epg=False)

    def _make_l3out_clone(self, ctx, l3out, vrf):
        clone_l3out = super(EdgeNatStrategy, self)._make_l3out_clone(
            ctx, l3out, vrf)
        # TODO(amitbose) modify the clone_l3out node-profile etc
        return clone_l3out
