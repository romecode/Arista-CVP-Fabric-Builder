# Arista-CVP-Fabric-Builder

 

A templating engine which leverages recipies for template to configlet compilation using variables injected from CSV files, global, and recipe definitions. The templates support sections with tests ```@...@{tests}```, iterables/options ```[...]``` or ```[...]else[...]```, and plain old variables ```{...}```.

The structure lends itelf for quick compilation of recurring structures found in network configurations.

The engine parses the template and compiles the defined structures using a combination of CSV file, recipe, and global variable definitions.


1. Template Definition

Create a section in the templates.conf e.g.

```
[<templateName>]
basetemplate =

    this is my config
    spanning multiple
    lines
        ~use a tilde to tab over
            ~~or multiple tildes
    
skip_container = <container> (this is optional)
```

A gotcha with defining multiline templates is that whitespace is not respected, therefore ~ will be replaced with a tab upon compilation.

2. Special syntax

Within the basetemplate definition above, the engine supports the following structures:

A. Variables

```
{<variableName>}
```
The ```<variableName>``` will search the following sources:
a. global.conf

This file contains two sections: global and the user-defined sections (e.g. evpn).

Variables defined in the deployed section supercede the global definition unless found in the source csv; i.e. variable search first checks the source csv, then recipe, then the global namespace.

Variables can also be extended to support a more complex operation but require definition within the python class.

This is considered advanced and requires implementation within the python code.

e.g.
```
@property
def spine_hostname_list(self):
    return [spine.hostname for spine in SPINES]
```

In the backend, all of the variables defined in the CSV automatically become dot-notation class properties.
Therefore if the CSV contains a header named ```<hostname>```, the corresponding class will have the respective property: ```<Switch>.hostname```.

Hence, when we define class properties using the @property decorator we can essentially turn a variable lookup into a python function to handle complex tasks.

We can even use templates within these functions as such:

```
@property
def underlay_bgp(self):
    template = TEMPLATES.get('underlay_bgp')
```

B. Sections with tests

```
@
config goes here
@{<tests>}
```
This structure is a section which fails completely if ```<tests>``` resolve to false.
<tests> support multiple clauses separated by | i.e. ```{<test>|<test2>}``` will fail if ```<test>``` and ```<test2>``` are not defined.
Furthermore tests support equality/inequality (=/!=) checks ```{<test>|varName=equals}``` or ```{<test>|varName!=notEquals}```.
These can be used as needed to fail a section within a template. If we take a look at the EVPN recipie which calls for the mgmt|mlag|bgp-evpn templates, upon inspecting bgp-evpn we see a recurring test which checks the role:

e.g.

```
@
interface loopback1
~ip address {lo1}/32
!
@{role=leaf}
```
This section simply disappears from the compiled config if the role!=leaf.
Sections should be used when tests are needed.

C. Iterables/Options

```
[..{<someVar>}...]
```

Will behave as follows:
a. someVar is not defined: the option will be ignored and wiped; no output.
b. someVar is an iterable e.g. someVar = [1|2|3]: the option will iterate per variable; output will be:

```
..1...
..2...
..3...
```

If the option has a mixture of variables it will iterate what it can (if multiple iterables exist, they should all be the same length) and repeat static variables until iterables are exhausted.

Options also support an else clause e.g. ```[..{<someVar>}...]else[output this]```; if someVar fails, try the other option:

e.g.

```
@
[ip routing vrf {vrf_name}]
@{role=leaf}
```

This is a section which will iterate vrf_name only if role=leaf.

```
@
interface Vxlan1
    ~vxlan source-interface Loopback1
    ~vxlan virtual-router encapsulation mac-address mlag-system-id
    ~vxlan udp-port 4789
    [~vxlan vrf {vrf_name} vni {ibgp_vlan}]
@{role=leaf}
```

This is a section which will iterate vrf_name and ibgp_vlan if role=leaf.
You are free to use the structures however needed. Nesting is not supported.

D.

The syntax ```{10++}``` will return 10,20,30.. and ```{10+}``` will return 10,11,12.. if iterated.
Furthermore, ```{var+NUMBER}``` or ```{var++NUMBER}``` will return (+1 or NUMBER) or (+10 or NUMBER); NUMBER is optional.
```{var*NUMBER}``` will return a one time multiplication, ```{10*10}``` will return 100 respectively.

E. Pulling variables from supplementary CSV's

```
{filename#var}
```
Will attempt to open the file filename.csv in the current directory and build iterators with the data found in the CSV.

e.g.

given filename.csv:

```
vlan,description
10,vlan 10
20,vlan 20
30,vlan 30
```

and the iterable:

```
[...{filename#vlan}...]
```

will output:

```
...10...
...20...
...30...
```

3. Execution cycle

On load ```python builder.py``` the application sets up a command prompt.
TODO: Define commands and usage

To execute a recipe: ```deploy <recipe>```

recipe is the user-defined section e.g. evpn: ```deploy evpn``` will inject the recipe templates ```recipe = [mgmt|mlag|bgp-evpn]``` into each switch instance as defined in the devices.csv.

Tasks are then created per device which compile the recipe templates per device along with the section and global variables as supplements.

CVP API's are leveraged to create a task per configlet template per device respectively.

4. Variable definition global/recipe

```
foo =
foo = bar
foo = [bar1|bar2|...]
```
 
```|``` are replaced with commas both in the CSV and config definitions. You can see an example of | in the CSV under mlag_int.

5. Template compile cycle

The basetemplate definition first parses sections, then options/iterables, then standalone vars; a template will fail completely if options/iterables or vars fail unless within a section.

Therefore, you can fail sections without failing the entire template. i.e. the template should only fail comletely if standalone options or vars fail.

A trick to fail an option without failing the template is to use ```[...]else[]``` where the option fails to an empty option (which is considered valid).

A ```@..[...]..@{test}``` section containing options will also fail entirely if variables within the options fail, granted the test passes. However, this can also be mitigated using the ```[...]else[]``` syntax, or checking for the variable within the section test itself, up to you.


As a full example let's build a template which maps VLAN's to VNI's.

given filename.csv:

```
vlan,description
10,vlan 10
20,vlan 20
30,vlan 30
```

1. Create the user-defined section in global.conf

```
#the name below is what you "deploy", which compiles the recipe templates for each device in fabric_parameters.csv 
#the default configlet naming scheme is TEMPLATENAME-HOSTNAME-CONFIG
[vlan-to-vni]
#recipe must be a list even with one option
recipe = [vlan-to-vni]

#here you can define variables which supercede the global config
#i.e. you can just as easily define the vlans here as such

#vlan = [10|20|30]
#description = [vlan 10|vlan 20|vlan30]

#however this might be cumbersome for large lists so the option of loading a csv is available
```

2. Create the template definition for vlan-to-vni in templates.conf

```
#the name below is what you invoke in the recipes
[vlan-to-vni]
basetemplate =
 
    router bgp {asn}
      [~vlan {vlan-to-vni#vlan}
          ~~rd {lo1}:{vlan-to-vni#vlan*10}
          ~~route-target both {vlan-to-vni#vlan*10}:{vlan-to-vni#vlan*10}
          ~~redistribute learned
      ~!]
    !
    interface Vxlan1
        [~vxlan vlan {vlan-to-vni#vlan} vni {vlan-to-vni#vlan*10}]
    !
    [vlan {vlan-to-vni#vlan}
        ~name {vlan-to-vni#description}
    ~!]

skip_container = spine
```

On deployment:

```
>python builder.py
>(Cmd) deploy vlan-to-vni #notice here we "deploy" <userDefinedRecipe> in global.conf
```

Output:
```
************************************
VLAN-TO-VNI-DC1-LF07-CONFIG
************************************
router bgp 65104
	vlan 10
		rd 1.1.1.1:100
		route-target both 100:100
		redistribute learned
	!
	vlan 20
		rd 1.1.1.1:200
		route-target both 200:200
		redistribute learned
	!
	vlan 30
		rd 1.1.1.1:300
		route-target both 300:300
		redistribute learned
	!
!
interface Vxlan1
	vxlan vlan 10 vni 100
	vxlan vlan 20 vni 200
	vxlan vlan 30 vni 300
!
vlan 10
	name vlan 10
!
vlan 20
	name vlan 20
!
vlan 30
	name vlan 30
!
************************************
VLAN-TO-VNI-DC1-LF08-CONFIG
************************************
router bgp 65104
	vlan 10
		rd 1.1.1.1:100
		route-target both 100:100
		redistribute learned
	!
	vlan 20
		rd 1.1.1.1:200
		route-target both 200:200
		redistribute learned
	!
	vlan 30
		rd 1.1.1.1:300
		route-target both 300:300
		redistribute learned
	!
!
interface Vxlan1
	vxlan vlan 10 vni 100
	vxlan vlan 20 vni 200
	vxlan vlan 30 vni 300
!
vlan 10
	name vlan 10
!
vlan 20
	name vlan 20
!
vlan 30
	name vlan 30
!
```

If instead we:
 
```
>python builder.py
>(Cmd) deploy evpn
```

Output:

```
************************************
MGMT-DC1-LF07-CONFIG
************************************
hostname DC1-LF07
!
vrf definition EVPNMGMTVRF
	rd 1:1
!
interface Management1
	vrf forwarding EVPNMGMTVRF
	!
	ip address 10.20.30.29
!
management api http-commands
	no shutdown
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
management ssh
	idle-timeout 180
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
ip routing
!
ip routing vrf EVPNMGMTVRF
ip route vrf EVPNMGMTVRF 0.0.0.0/0 1.1.1.1
!
************************************
MLAG-DC1-LF07-CONFIG
************************************
ip virtual-router mac-address 00:1c:75:00:00:04
!
no spanning-tree vlan 4094
!
interface Ethernet49/1,49/2,49/3,49/4
	description MLAG Interface
	mtu 9214
	channel-group 1 mode actives
	speed forced 40g
!
vlan 4094
	name Mlag-peer-vlan
	trunk group mlag-peer
!
interface Vlan4094
	description MLAG Peer Address Network
	mtu 9214
	no autostate
	ip address 192.168.1.1/30
!
mlag configuration
	domain-id MLAGPEER
	local-interface Vlan4094
	peer-address 192.168.1.2
	peer-link Port-Channel1
	reload-delay mlag 780
	reload-delay non-mlag 1020
!
interface Port-Channel1
	description MLAGPEER
	load-interval 5
	switchport mode trunk
	switchport trunk group mlag-peer
	switchport trunk group vrfONE_IBGP_PEER
	switchport trunk group vrfTWO_IBGP_PEER
!
************************************
BGP-EVPN-DC1-LF07-CONFIG
************************************
2019-11-08 10:11:03.176446: Error building configlet section @peer-filter fi in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.176494: Error building configlet section @~bgp listen ra in bgp-evpn: test condition for role failed
interface Ethernet53/1
	description TO-DC1-SP01-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.107.2/31
!
interface Ethernet54/1
	description TO-DC1-SP02-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.207.2/31
!
ip routing
!

ip routing vrf vrfONE
ip routing vrf vrfTWO

service routing protocols model multi-agent
!
interface loopback0
	ip address 10.0.1.107/32
!

interface loopback1
	ip address 1.1.1.1/32
!


hardware tcam
system profile vxlan-routing
!


interface Vxlan1
	vxlan source-interface Loopback1
	vxlan virtual-router encapsulation mac-address mlag-system-id
	vxlan udp-port 4789
	vxlan vrf vrfONE vni 4080
	vxlan vrf vrfTWO vni 4081


router bgp 65104
	router-id 10.0.1.107
	distance bgp 20 200 200
	maximum-paths 4 ecmp 4


	neighbor EVPN-OVERLAY-PEERS peer-group
	neighbor EVPN-OVERLAY-PEERS remote-as 65001
	neighbor EVPN-OVERLAY-PEERS update-source Loopback0
	neighbor EVPN-OVERLAY-PEERS allowas-in 5
	neighbor EVPN-OVERLAY-PEERS ebgp-multihop 5
	neighbor EVPN-OVERLAY-PEERS send-community extended
	neighbor EVPN-OVERLAY-PEERS maximum-routes 12000
	neighbor IPv4-UNDERLAY-PEERS peer-group
	neighbor IPv4-UNDERLAY-PEERS remote-as 65001
	neighbor IPv4-UNDERLAY-PEERS allowas-in 1
	neighbor IPv4-UNDERLAY-PEERS send-community
	neighbor IPv4-UNDERLAY-PEERS maximum-routes 12000
	neighbor 10.0.1.1 peer-group EVPN-OVERLAY-PEERS
	neighbor 10.1.107.1 peer-group IPv4-UNDERLAY-PEERS
	neighbor 10.1.107.1 description TO-DC1-SP01
	neighbor 10.0.1.2 peer-group EVPN-OVERLAY-PEERS
	neighbor 10.1.207.1 peer-group IPv4-UNDERLAY-PEERS
	neighbor 10.1.207.1 description TO-DC1-SP02
	address-family evpn
		neighbor EVPN-OVERLAY-PEERS activate
	!
	address-family ipv4
		no neighbor EVPN-OVERLAY-PEERS activate
		network 10.0.1.107/32
		network 1.1.1.1/32
	!


	neighbor 192.168.1.2 remote-as 65104
	neighbor 192.168.1.2 next-hop-self
	neighbor 192.168.1.2 allowas-in 1
	neighbor 192.168.1.2 maximum-routes 12000


	vrf vrfONE
		rd 10.0.1.107:4080
		route-target import 1000:4080
		route-target export 1000:4080
		neighbor 192.168.1.6 remote-as 65104
		neighbor 192.168.1.6 next-hop-self
		neighbor 192.168.1.6 update-source Vlan4080
		neighbor 192.168.1.6 allowas-in 1
		neighbor 192.168.1.6 maximum-routes 12000
		redistribute connected
	!
	vrf vrfTWO
		rd 10.0.1.107:4081
		route-target import 1000:4081
		route-target export 1000:4081
		neighbor 192.168.1.6 remote-as 65104
		neighbor 192.168.1.6 next-hop-self
		neighbor 192.168.1.6 update-source Vlan4081
		neighbor 192.168.1.6 allowas-in 1
		neighbor 192.168.1.6 maximum-routes 12000
		redistribute connected
	!
************************************
MGMT-DC1-LF08-CONFIG
************************************
hostname DC1-LF08
!
vrf definition EVPNMGMTVRF
	rd 1:1
!
interface Management1
	vrf forwarding EVPNMGMTVRF
	!
	ip address 10.20.30.30
!
management api http-commands
	no shutdown
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
management ssh
	idle-timeout 180
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
ip routing
!
ip routing vrf EVPNMGMTVRF
ip route vrf EVPNMGMTVRF 0.0.0.0/0 1.1.1.1
!
************************************
MLAG-DC1-LF08-CONFIG
************************************
ip virtual-router mac-address 00:1c:75:00:00:04
!
no spanning-tree vlan 4094
!
interface Ethernet49/1,49/2,49/3,49/4
	description MLAG Interface
	mtu 9214
	channel-group 1 mode actives
	speed forced 100g
!
vlan 4094
	name Mlag-peer-vlan
	trunk group mlag-peer
!
interface Vlan4094
	description MLAG Peer Address Network
	mtu 9214
	no autostate
	ip address 192.168.1.2/30
!
mlag configuration
	domain-id MLAGPEER
	local-interface Vlan4094
	peer-address 192.168.1.1
	peer-link Port-Channel1
	reload-delay mlag 780
	reload-delay non-mlag 1020
!
interface Port-Channel1
	description MLAGPEER
	load-interval 5
	switchport mode trunk
	switchport trunk group mlag-peer
	switchport trunk group vrfONE_IBGP_PEER
	switchport trunk group vrfTWO_IBGP_PEER
!
************************************
BGP-EVPN-DC1-LF08-CONFIG
************************************
2019-11-08 10:11:03.179228: Error building configlet section @peer-filter fi in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.179277: Error building configlet section @~bgp listen ra in bgp-evpn: test condition for role failed
interface Ethernet53/1
	description TO-DC1-SP01-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.108.2/31
!
interface Ethernet54/1
	description TO-DC1-SP02-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.208.2/31
!
ip routing
!

ip routing vrf vrfONE
ip routing vrf vrfTWO

service routing protocols model multi-agent
!
interface loopback0
	ip address 10.0.1.108/32
!

interface loopback1
	ip address 1.1.1.1/32
!


hardware tcam
system profile vxlan-routing
!


interface Vxlan1
	vxlan source-interface Loopback1
	vxlan virtual-router encapsulation mac-address mlag-system-id
	vxlan udp-port 4789
	vxlan vrf vrfONE vni 4080
	vxlan vrf vrfTWO vni 4081


router bgp 65104
	router-id 10.0.1.108
	distance bgp 20 200 200
	maximum-paths 4 ecmp 4


	neighbor EVPN-OVERLAY-PEERS peer-group
	neighbor EVPN-OVERLAY-PEERS remote-as 65001
	neighbor EVPN-OVERLAY-PEERS update-source Loopback0
	neighbor EVPN-OVERLAY-PEERS allowas-in 5
	neighbor EVPN-OVERLAY-PEERS ebgp-multihop 5
	neighbor EVPN-OVERLAY-PEERS send-community extended
	neighbor EVPN-OVERLAY-PEERS maximum-routes 12000
	neighbor IPv4-UNDERLAY-PEERS peer-group
	neighbor IPv4-UNDERLAY-PEERS remote-as 65001
	neighbor IPv4-UNDERLAY-PEERS allowas-in 1
	neighbor IPv4-UNDERLAY-PEERS send-community
	neighbor IPv4-UNDERLAY-PEERS maximum-routes 12000
	neighbor 10.0.1.1 peer-group EVPN-OVERLAY-PEERS
	neighbor 10.1.108.1 peer-group IPv4-UNDERLAY-PEERS
	neighbor 10.1.108.1 description TO-DC1-SP01
	neighbor 10.0.1.2 peer-group EVPN-OVERLAY-PEERS
	neighbor 10.1.208.1 peer-group IPv4-UNDERLAY-PEERS
	neighbor 10.1.208.1 description TO-DC1-SP02
	address-family evpn
		neighbor EVPN-OVERLAY-PEERS activate
	!
	address-family ipv4
		no neighbor EVPN-OVERLAY-PEERS activate
		network 10.0.1.108/32
		network 1.1.1.1/32
	!


	neighbor 192.168.1.1 remote-as 65104
	neighbor 192.168.1.1 next-hop-self
	neighbor 192.168.1.1 allowas-in 1
	neighbor 192.168.1.1 maximum-routes 12000


	vrf vrfONE
		rd 10.0.1.108:4080
		route-target import 1000:4080
		route-target export 1000:4080
		neighbor 192.168.1.6 remote-as 65104
		neighbor 192.168.1.6 next-hop-self
		neighbor 192.168.1.6 update-source Vlan4080
		neighbor 192.168.1.6 allowas-in 1
		neighbor 192.168.1.6 maximum-routes 12000
		redistribute connected
	!
	vrf vrfTWO
		rd 10.0.1.108:4081
		route-target import 1000:4081
		route-target export 1000:4081
		neighbor 192.168.1.6 remote-as 65104
		neighbor 192.168.1.6 next-hop-self
		neighbor 192.168.1.6 update-source Vlan4081
		neighbor 192.168.1.6 allowas-in 1
		neighbor 192.168.1.6 maximum-routes 12000
		redistribute connected
	!
************************************
MGMT-DC1-SP02-CONFIG
************************************
hostname DC1-SP02
!
vrf definition EVPNMGMTVRF
	rd 1:1
!
interface Management1
	vrf forwarding EVPNMGMTVRF
	!
	ip address 10.20.30.22
!
management api http-commands
	no shutdown
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
management ssh
	idle-timeout 180
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
ip routing
!
ip routing vrf EVPNMGMTVRF
ip route vrf EVPNMGMTVRF 0.0.0.0/0 1.1.1.1
!
************************************
BGP-EVPN-DC1-SP02-CONFIG
************************************
2019-11-08 10:11:03.180990: Error building configlet section @[ip routing vr in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.181035: Error building configlet section @interface loop in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.181104: Error building configlet section @hardware tcams in bgp-evpn: test condition for is_jericho failed
2019-11-08 10:11:03.181210: Error building configlet section @interface Vxla in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.181426: Error building configlet section @~neighbor EVPN in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.181519: Error building configlet section @~neighbor {mla in bgp-evpn: test condition for role,mlag_neighbor failed
2019-11-08 10:11:03.181832: Error building configlet section @[~vrf {vrf_nam in bgp-evpn: test condition for role failed
interface Ethernet6/2
	description TO-DC1-LF07-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.207.1/31
!
interface Ethernet6/1
	description TO-DC1-LF08-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.208.1/31
!
ip routing
!

service routing protocols model multi-agent
!
interface loopback0
	ip address 10.0.1.2/32
!




peer-filter filter-peers
	10 match as-range 65104-65105 result accept
!

router bgp 65001
	router-id 10.0.1.2
	distance bgp 20 200 200
	maximum-paths 4 ecmp 4

	bgp listen range 10./27 peer-group EVPN-OVERLAY-PEERS peer-filter filter-peers
	bgp listen range 10.10.0.0/26 peer-group IPv4-UNDERLAY-PEERS peer-filter filter-peers
	neighbor EVPN-OVERLAY-PEERS peer-group
	neighbor EVPN-OVERLAY-PEERS next-hop-unchanged
	neighbor EVPN-OVERLAY-PEERS update-source Loopback0
	neighbor EVPN-OVERLAY-PEERS ebgp-multihop 5
	neighbor EVPN-OVERLAY-PEERS send-community extended
	neighbor EVPN-OVERLAY-PEERS maximum-routes 12000
	neighbor IPv4-UNDERLAY-PEERS peer-group
	neighbor IPv4-UNDERLAY-PEERS maximum-routes 12000
	!
	address-family evpn
		bgp next-hop-unchanged
		neighbor EVPN-OVERLAY-PEERS activate
	!
	address-family ipv4
		no neighbor EVPN-OVERLAY-PEERS activate
		network 10.0.1.2/32
	!
************************************
MGMT-DC1-SP01-CONFIG
************************************
hostname DC1-SP01
!
vrf definition EVPNMGMTVRF
	rd 1:1
!
interface Management0
	vrf forwarding EVPNMGMTVRF
	!
	ip address 10.20.30.21
!
management api http-commands
	no shutdown
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
management ssh
	idle-timeout 180
	!
	vrf EVPNMGMTVRF
		no shutdown
	!
!
ip routing
!
ip routing vrf EVPNMGMTVRF
ip route vrf EVPNMGMTVRF 0.0.0.0/0 1.1.1.1
!
************************************
BGP-EVPN-DC1-SP01-CONFIG
************************************
2019-11-08 10:11:03.182594: Error building configlet section @[ip routing vr in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.182640: Error building configlet section @interface loop in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.182713: Error building configlet section @hardware tcams in bgp-evpn: test condition for is_jericho failed
2019-11-08 10:11:03.182821: Error building configlet section @interface Vxla in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.183031: Error building configlet section @~neighbor EVPN in bgp-evpn: test condition for role failed
2019-11-08 10:11:03.183126: Error building configlet section @~neighbor {mla in bgp-evpn: test condition for role,mlag_neighbor failed
2019-11-08 10:11:03.183414: Error building configlet section @[~vrf {vrf_nam in bgp-evpn: test condition for role failed
interface Ethernet3/6/1
	description TO-DC1-LF07-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.107.1/31
!
interface Ethernet3/6/2
	description TO-DC1-LF08-UNDERLAY
	mtu 9214
	no switchport
	speed forced 100g
	ip address 10.1.108.1/31
!
ip routing
!

service routing protocols model multi-agent
!
interface loopback0
	ip address 10.0.1.1/32
!




peer-filter filter-peers
	10 match as-range 65104-65105 result accept
!

router bgp 65001
	router-id 10.0.1.1
	distance bgp 20 200 200
	maximum-paths 4 ecmp 4

	bgp listen range 10./27 peer-group EVPN-OVERLAY-PEERS peer-filter filter-peers
	bgp listen range 10.10.0.0/26 peer-group IPv4-UNDERLAY-PEERS peer-filter filter-peers
	neighbor EVPN-OVERLAY-PEERS peer-group
	neighbor EVPN-OVERLAY-PEERS next-hop-unchanged
	neighbor EVPN-OVERLAY-PEERS update-source Loopback0
	neighbor EVPN-OVERLAY-PEERS ebgp-multihop 5
	neighbor EVPN-OVERLAY-PEERS send-community extended
	neighbor EVPN-OVERLAY-PEERS maximum-routes 12000
	neighbor IPv4-UNDERLAY-PEERS peer-group
	neighbor IPv4-UNDERLAY-PEERS maximum-routes 12000
	!
	address-family evpn
		bgp next-hop-unchanged
		neighbor EVPN-OVERLAY-PEERS activate
	!
	address-family ipv4
		no neighbor EVPN-OVERLAY-PEERS activate
		network 10.0.1.1/32
	!
```
 