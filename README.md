# Arista-CVP-Fabric-Builder

 

A templating engine which leverages recipies for template to configlet compilation using variables injected from CSV files, global, and recipe definitions. The templates support sections with tests ```@...@{tests}```, iterables/options ```[...]``` or ```[...]else[...]```, and plain old variables ```{...}```.

The structure lends itelf for quick compilation of recurring structures found in network configurations.

The engine parses the template and compiles the defined structures using a combination of CSV file, recipe, and global variable definitions.

We will use the EVPN recipe to fully demonstrate how to define your own templates and recipes.

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
The <variableName> will be search the following sources:
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

In the backend, all of the variables defined in the CSV become dot-notation class properties automatically.
Therefore if the CSV contains a header named <hostname>, the corresponding class will have the respective property: <Switch>.hostname

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
This structure is a section which fails completely if <tests> resolve to false.
<tests> support multiple clauses separated by | i.e. ```{<test>|<test2>}``` will fail if <test> and <test2> are not defined.
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

1. Create the user-defined section in global.conf

```
[vlan-to-vni]
recipe = vlan-to-vni
```

2. Create the template definition for vlan-to-vni in templates.conf

```
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

>python builder.py
>(Cmd) deploy vlan-to-vni


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
 

 