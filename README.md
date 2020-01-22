# Arista-CVP-Fabric-Builder

**INSTALL**
```
pip install virtualenv
mkdir fabric_builder; cd fabric_builder
virtualenv .
source bin/activate
pip install urllib3
pip install xlrd
pip install git+https://github.com/aristanetworks/cvprac.git@develop
pip install git+https://github.com/romecode/Arista-CVP-Fabric-Builder.git
pip install configparser
```

This tool is a complete day1/day2 Arista CVP solution for compiling configlets from templates, creating and assigning them in CVP, and appending new config.
The template parsing engine is made to be fully customizable and extendable without the need to touch python code (very complex situations aside).

**FEATURES:**
- Add/remove CSV source file columns/data as you wish
- Compile one or more templates per run (fully customizable)
- Define recipes for what templates to compile (fully customizable)
- Override global variables within recipes
- Variables for templates can be sourced from CSV, recipe, global, external CSV, telemetry
- Template variables support math operations, comparisons, truncation
- A multitude of predefined syntax to support grouping, iterations, and other structures
- Talks to CVP via REST API
- Work with existing CVP devices or CSV defined

**CORE FILES:**
- builder.py contains all the Python code
- fabric_parameters.csv is the CSV which let's you define switch parameters (the headers are automatically available within the templates)
- global.conf defines the static global variables and additional recipes along with their own static variables (which override global variables with the same name)
- templates.conf defines the templates themselves

**EXAMPLE:**

NOTE: The below .conf files are parsed via the Python configParser library and they have their own syntax.
In general:
1. The square brackets define a new section
2. Variables are assigned as such ```variableName = 123```
3. \# are comments

Our fabric_parameters.csv contents are as follows:
The headers ```sn, hostname, role, container``` are absolutely required. Furthermore, ```role``` should alwas be either ```spine``` or ```leaf``` for differentiation.

```
SN			HOSTNAME	ROLE	CONTAINER
HSH14085036	DC1-SP01	spine	DC1-Spines
JPE18372884	DC1-SP02	spine	DC1-Spines
JAS16420034	DC1-LF07	leaf	DC1-Leaf	
JAS16420035	DC1-LF08	leaf	DC1-Leaf
```

1. Define your template in templates.conf 

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
```

Here, templateName1 is the template name.
basetemplate is the template definition which is a multiline variable, it requires a tab for each following line.

2. Define the recipe which defines what templates to compile in global.conf

```
[myRecipeName]
recipe = [templateName1]
mode = day1
```

myRecipeName is the section within global.conf where you define the recipe, mode, singleton, and other options. Those will be discussed in full detail later.
recipe is a list of templates to compile (is always defined as a list).
mode is set to day1, which means this recipe and all requested templates will compile for each device in fabric_parameters.csv (the other option is day2).


3. To run

First, activate virtualenv: cd to the fabric_builder folder and run ```source bin/activate```
run ```python builder.py```

```
>python builder.py
2019-11-18 12:22:24.203974: Successfully authenticated to CVP
Type ? for available commands
builder>deploy myRecipeName
```

The program sets up it's own command interpreter ```builder>``` from which we use the ```deploy``` command and specify the recipe to execute (this is what we defined in global.conf)
Since debug = True, the program will not touch CVP and simply print what it would have pushed to CVP.

```
builder>deploy myRecipeName
2019-11-18 14:48:28.278175: Device init hsh14085036, Role: spine, CVP found: (x)
2019-11-18 14:48:28.278265: Device init jpe18372884, Role: spine, CVP found: (x)
2019-11-18 14:48:28.278324: Device init jas16420034, Role: leaf, CVP found: (x)
2019-11-18 14:48:28.278377: Device init jas16420035, Role: leaf, CVP found: (x)
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
**************************************************
**************************************************
TEMPLATENAME1-DC1-LF08-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP02-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
**************************************************
builder>
```

Each time a command is run, the global.conf, templates.conf, and fabric_parameters.csv are reloaded and any modifications are absorbed into the builder without having to restart.
Examining the output... we can see that it initialized the fabric_parameters.csv and ran once per device.
So we can see that configlets are automatically named using the template name, hostname, and CONFIG i.e. for this run: TEMPLATENAME1-DC-1-LF07-CONFIG and the resulting config as we defined it.
This recipe compiled once per device in the csv according to the parameters. Now let's modify the template as such and introduce some new concepts.

Our new template is now:

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
```

The syntax ```{variableName}``` searches the CSV, recipe, and global config in that order and injects the requested variableName into the compiled template.
We can see that for each device it found ```{hostname}``` and ```{role}``` and compiled accordingly.

rerun the template ```>deploy myRecipeName```

resulting output:
```
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF07
role is leaf
**************************************************
**************************************************
TEMPLATENAME1-DC1-LF08-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF08
role is leaf
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP02-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP02
role is spine
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
**************************************************
```

To add new variables simply modify the CSV e.g.

```
SN			HOSTNAME	ROLE	CONTAINER	NEWVARIABLE
HSH14085036	DC1-SP01	spine	DC1-Spines	switch1
JPE18372884	DC1-SP02	spine	DC1-Spines	switch2
JAS16420034	DC1-LF07	leaf	DC1-Leaf	switch3
JAS16420035	DC1-LF08	leaf	DC1-Leaf
```

and modify the template:

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
	we added a new variable {newvariable}
```

rerun the template ```>deploy myRecipeName```

resulting output:
```
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF07
role is leaf
we added a new variable switch3
**************************************************
**************************************************
TEMPLATENAME1-DC1-LF08-CONFIG
**************************************************
2019-11-18 15:03:38.094435: Error building configlet templateName1: global/device definition for newvariable undefined

**************************************************
**************************************************
TEMPLATENAME1-DC1-SP02-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP02
role is spine
we added a new variable switch2
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
we added a new variable switch1
**************************************************
```

We see that the newvariable was automatically made available to the compiler.
Also notice that we did not define one for DC1-LF08 which resulted in the template failing to compile.

This is a perfect time to introduce the concept as to how the templating parser works and how it can be customized.
Right now the basetemplate is simply some text and some variables and the entire template failed for DC1-LF08 because of this one missing variable.
At this point, the template behaves as an entire whole and will fail if any of the variables are undefined.

Let's introduce the concept of ```pruning```. This should be a familiar term for Network Engineers.
The template parser was built with the concept of ```pruning``` to be able to define groups of config, i.e. what if we wanted the template to still compile but simply prune the offending line?

There are a few syntactical structures to allow this:

1. We can wrap the line in brackets

e.g.
```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
	[we added a new variable {newvariable}]
```

Output:
```
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF07
role is leaf
we added a new variable switch3
**************************************************
**************************************************
TEMPLATENAME1-DC1-LF08-CONFIG
**************************************************
Mon Nov 18 15:50:39 2019: Pruned configlet option [we added a new... in templateName1: variable newvariable undefined
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF08
role is leaf
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP02-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP02
role is spine
we added a new variable switch2
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
we added a new variable switch1
**************************************************
```

Now DC1-LF08 compiled the template but simply pruned off the offending line.
***NOTE lines wrapped in brackes behave differently in other syntax options to be explored later in the document.
Just rememeber that by themselves they simply prune from the template, we can see the prune itself is logged (but not part of the configlet).

There is another way to write the bracket syntax, and by the way, they can span multiple lines e.g.

```
[this config
is perfectly
valid {newvariable}]
```

The other way to define brackets is like so ```[config to prune on failure {newvariable}]else[use this config instead]```

e.g.

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
	[we added a new variable {newvariable}
	spanning multiple lines
	]else[use this config instead]
```

Output:
```
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF07
role is leaf
we added a new variable switch3
spanning multiple lines
**************************************************
**************************************************
TEMPLATENAME1-DC1-LF08-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF08
role is leaf
use this config instead
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP02-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP02
role is spine
we added a new variable switch2
spanning multiple lines
**************************************************
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
we added a new variable switch1
spanning multiple lines
**************************************************
```

So brackets as we know them support the following syntax:
1. By themselves they group together multiple lines of config which gets pruned if a variable is undefined.
2. They support multiple lines
3. They support a fallback clause via else

To recap. Templates are compiled and error out if variables are missing. To preserve the template we can enclose those lines in brackets to prune only the grouped config.

Blank brackets compile to whitespace e.g. 

```
[]
```

or

```
[]else[]
```
will compile to whitespace and not throw an error since a blank config is technically correct and does not offend the parser.


Let's now look at a more complex template

```
[mgmt]
basetemplate = 

	hostname {hostname}
	!
	[vrf definition {mgmt_vrf}
		~rd 1:1
	!]
	interface Management{mgmt_int}
		~[vrf forwarding {mgmt_vrf}
		~!]
		~ip address {mgmt_ip}
	!
	management api http-commands
		~no shutdown
		~!
		~[vrf {mgmt_vrf}
			~~no shutdown
		~!]
	!
	management ssh
		~idle-timeout 180
		~!
		~[vrf {mgmt_vrf}
			~~no shutdown
		~!]
	!
	ip routing
	!
	[ip routing vrf {mgmt_vrf}
	ip route vrf {mgmt_vrf} 0.0.0.0/0 {mgmt_gw}
	!]else[ip route 0.0.0.0/0 {mgmt_gw}
	!]
```

Let's inspect. This is a management template which compiles accordingly if vrf's are defined.
Since management VRF's are usually global for the infrastructure, we do not need a "per switch" variable in the fabric_parameters.csv, we can simply define ``` mgmt_vrf, mgmt_gw ``` in the global context.

e.g. 

In global.conf:

```
[global]
debug = True

mgmt_gw = 1.1.1.1
mgmt_vrf = MGMTVRF
```

Also modify the recipe to include this template.

```
[myRecipeName]
recipe = [templateName1|mgmt]
mode = day1
```

Output:
```
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF07
role is leaf
we added a new variable switch3
spanning multiple lines
**************************************************
**************************************************
MGMT-DC1-LF07-CONFIG
**************************************************
hostname DC1-LF07
!
vrf definition MGMTVRF
	rd 1:1
!
interface Management1
	vrf forwarding MGMTVRF
	!
	ip address 10.20.30.29
!
management api http-commands
	no shutdown
	!
	vrf MGMTVRF
		no shutdown
	!
!
management ssh
	idle-timeout 180
	!
	vrf MGMTVRF
		no shutdown
	!
!
ip routing
!
ip routing vrf MGMTVRF
ip route vrf MGMTVRF 0.0.0.0/0 1.1.1.1
!
**************************************************
**************************************************
TEMPLATENAME1-DC1-LF08-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF08
role is leaf
use this config instead
**************************************************
**************************************************
MGMT-DC1-LF08-CONFIG
**************************************************
hostname DC1-LF08
!
vrf definition MGMTVRF
	rd 1:1
!
interface Management1
	vrf forwarding MGMTVRF
	!
	ip address 10.20.30.30
!
management api http-commands
	no shutdown
	!
	vrf MGMTVRF
		no shutdown
	!
!
management ssh
	idle-timeout 180
	!
	vrf MGMTVRF
		no shutdown
	!
!
ip routing
!
ip routing vrf MGMTVRF
ip route vrf MGMTVRF 0.0.0.0/0 1.1.1.1
!
**************************************************
```

The remainder of the output was truncated, but you get the idea. Since ```mgmt_gw, mgmt_vrf``` are defined the template compiles accordingly.

So to rehash... when searching for ```{mgmt_vrf}``` and ```{mgmt_gw}``` the parser first looks at the fabric_parameters.csv, there is no column with either name.
It then searches the recipe and fails again, finally it finds both variables defined in the global section and everything compiles.

We can also see that for each device all the templates in the recipe list are compiled.

We could also have defined the ```mgmt``` variables in the recipe section like so.


```
[myRecipeName]
recipe = [mgmt]
mode = day1
mgmt_gw = 1.1.1.1
mgmt_vrf = MGMTVRF
```

and gotten the same results.

These definitions take precedence over the global section, i.e. they are used instead.

Let's undefine mgmt_vrf and remove ```myTemplateName``` from the recipe for clarity; what would you expect the output to be now?

```
[global]
debug = True

mgmt_gw = 1.1.1.1
mgmt_vrf = 
```

Output:
```
**************************************************
MGMT-DC1-LF07-CONFIG
**************************************************
Mon Nov 18 16:10:38 2019: Pruned configlet option [vrf definition... in mgmt: variable mgmt_vrf undefined
Mon Nov 18 16:10:38 2019: Pruned configlet option [vrf forwarding... in mgmt: variable mgmt_vrf undefined
Mon Nov 18 16:10:38 2019: Pruned configlet option [vrf {mgmt_vrf}... in mgmt: variable mgmt_vrf undefined
Mon Nov 18 16:10:38 2019: Pruned configlet option [vrf {mgmt_vrf}... in mgmt: variable mgmt_vrf undefined
hostname DC1-LF07
!

interface Management1

	ip address 10.20.30.29
!
management api http-commands
	no shutdown
	!

!
management ssh
	idle-timeout 180
	!

!
ip routing
!
ip route 0.0.0.0/0 1.1.1.1
!
**************************************************
```

As expected, all the bracketed groups which relied on ```mgmt_vrf``` were pruned from the config and we are left with a basic non vrf mgmt configlet.

Here is a perfect example of the bracket else clause:

```
[ip routing vrf {mgmt_vrf}
ip route vrf {mgmt_vrf} 0.0.0.0/0 {mgmt_gw}
!]else[ip route 0.0.0.0/0 {mgmt_gw}
!]
```


So you should be able to see now the structure and concepts behind the template syntax. One is free to define the templates however it makes most sense both logically and structurally.

We have only scratched the surface of the capabilities so far.

Let's go back to the recipe configuration and go back to working with only templateName1.
We will also add two additional variables which are lists and perform some iterations.

```
[myRecipeName]
recipe = [templateName1]
mode = day1
listVariable1 = [10|20|30|40]
listVariable2 = [300|400|500|600]
singleVariable = I am a single Variable
```

and modify our template:

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
	
	[we added a new variable {newvariable}
	spanning multiple lines
	]else[use this config instead]
	
	We are now demonstrating iterations and math
	
	[this will iterate automatically for lists {listVariable1}
	and iterate lists together {listVariable2}
	and keep static variables {singleVariable}]
	
```

Output:

```
**************************************************
TEMPLATENAME1-DC1-LF07-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-LF07
role is leaf
we added a new variable switch3
spanning multiple lines

We are now demonstrating iterations and math
this will iterate automatically for lists 10
and iterate lists together 300
and keep static variables I am a single Variable
this will iterate automatically for lists 20
and iterate lists together 400
and keep static variables I am a single Variable
this will iterate automatically for lists 30
and iterate lists together 500
and keep static variables I am a single Variable
this will iterate automatically for lists 40
and iterate lists together 600
and keep static variables I am a single Variable
**************************************************
```

So the parser will iterate list variables in brackets and walk lists together if those lists are the same length.
If the list lengths are not of equal length the parser will stop iterating when the shortest list ends.

i.e. if we modify ```listVariable2 = [300|400|500]```

The output ends up being:

```
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
we added a new variable switch1
spanning multiple lines

We are now demonstrating iterations and math
this will iterate automatically for lists 10
and iterate lists together 300
and keep static variables I am a single Variable
this will iterate automatically for lists 20
and iterate lists together 400
and keep static variables I am a single Variable
this will iterate automatically for lists 30
and iterate lists together 500
and keep static variables I am a single Variable
**************************************************
```

We can observe that the iterations stop after the last variable runs out.

Let's introduce some math operations which are supported on these iterators and numeric variables in general.

```
[myRecipeName]
recipe = [templateName1]
mode = day1
#compile_for = [JAS16420034|DC1-LF07]
listVariable1 = [10|20|30|40]
listVariable3 = [300|400|500|600]
singleVariable = 555
```

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
	
	[we added a new variable {newvariable}
	spanning multiple lines
	]else[use this config instead]
	
	We are now demonstrating iterations and math
	
	[demo multiplication {listVariable1*10}
	demo one plus sign {listVariable3+}
	demo two plus signs {listVariable3++}
	demo plus with quantity {listVariable3+100}
	demo plus on static variable {singleVariable+}]
	
```

Output:

```
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
we added a new variable switch1
spanning multiple lines

We are now demonstrating iterations and math
demo multiplication 100
demo one plus sign 301
demo two plus signs 310
demo plus with quantity 400
demo plus on static variable 555
demo multiplication 200
demo one plus sign 401
demo two plus signs 410
demo plus with quantity 500
demo plus on static variable 556
demo multiplication 300
demo one plus sign 501
demo two plus signs 510
demo plus with quantity 600
demo plus on static variable 557
demo multiplication 400
demo one plus sign 601
demo two plus signs 610
demo plus with quantity 700
demo plus on static variable 558
**************************************************
```

Math operations can also be performed on numeric values right in the template e.g.

```
[templateName1]
basetemplate =
	this is the config for template1
	which spans
	multiple lines
	which now requires variables
	we are compiling for {hostname}
	role is {role}
	
	[we added a new variable {newvariable}
	spanning multiple lines
	]else[use this config instead]
	
	We are now demonstrating iterations and math
	
	[demo multiplication {10*10}
	while iterating {listVariable1}]
```

```
**************************************************
TEMPLATENAME1-DC1-SP01-CONFIG
**************************************************
this is the config for template1
which spans
multiple lines
which now requires variables
we are compiling for DC1-SP01
role is spine
we added a new variable switch1
spanning multiple lines

We are now demonstrating iterations and math
demo multiplication 10
while iterating 10
demo multiplication 100
while iterating 20
demo multiplication 1000
while iterating 30
demo multiplication 10000
while iterating 40
**************************************************
```

Variables defined as a math operation on numeric values will start at the initialized value and continue with the math operation for subsequent iterations.

So far we covered:
1. Plain text templates and how to run them
2. How to add variables to CSV, recipe, and global config
3. Basic usage of variables in templates
4. Pruning via defined groups using [] and []else[]
5. Iterating lists

Now what we are familiar with the basic functionality, let's introduce some more ways to group chunks of the template in order to build more complex strutcures.

Let's introduce the syntax first this time:

```
@
Anything enclosed with the "at" symbol
is treated as a major group.

Variabled defined here {variable}
which do not resolve will prune the entire group they belong to.

Iterables/options with the plain [] syntax
will also prune the whole group.

However if there is a necessity to keep the section due to failing iterables you can do so with the []else[] syntax.
What happens in this case is that the first [] fails but falls back to the else[] which is considered valid, therefore the section stays.
@
```

There is also another syntax which performs checks before the section is even considered for compilation and the syntax is as follows:

```
@
This is that same section 
however now we have tests which have to pass
before the parser even considers it
@{testVariablesGoHere}
```

Here is an example of an EVPN template which builds the BGP config and uses all the complex syntax structures just introduced.

```
[bgp-evpn]
basetemplate = 

	{underlay_bgp}
	
	ip routing
	!
	
	@
	[ip routing vrf {vrf_name}]
	@{role=leaf}
	
	service routing protocols model multi-agent
	!
	
	interface loopback0
		~ip address {lo0}/32
	!
	
	@
	interface loopback1
		~ip address {lo1}/32
	!
	@{role=leaf}
	
	@
	hardware tcam
	system profile vxlan-routing
	!
	@{is_jericho}
	
	@
	interface Vxlan1
		~vxlan source-interface Loopback1
		~vxlan virtual-router encapsulation mac-address mlag-system-id
		~vxlan udp-port 4789
		[~vxlan vrf {vrf_name} vni {ibgp_vlan}]
	@{role=leaf}
		
	@
	peer-filter filter-peers
		[~{10++} match as-range {asn_range} result accept]
	!
	@{role=spine}
	
	router bgp {asn}
		~router-id {lo0}
		~distance bgp 20 200 200
		~maximum-paths 4 ecmp 4
		
		@
		~bgp listen range {evpn_overlay_range} peer-group EVPN-OVERLAY-PEERS peer-filter filter-peers
		~bgp listen range {ipv4_underlay_range} peer-group IPv4-UNDERLAY-PEERS peer-filter filter-peers
		
		~neighbor EVPN-OVERLAY-PEERS peer-group
		~neighbor EVPN-OVERLAY-PEERS next-hop-unchanged
		~neighbor EVPN-OVERLAY-PEERS update-source Loopback0
		~neighbor EVPN-OVERLAY-PEERS ebgp-multihop 5
		~neighbor EVPN-OVERLAY-PEERS send-community extended
		~neighbor EVPN-OVERLAY-PEERS maximum-routes 12000 
		~neighbor IPv4-UNDERLAY-PEERS peer-group
		~neighbor IPv4-UNDERLAY-PEERS maximum-routes 12000 
		~!
		~address-family evpn
			~~bgp next-hop-unchanged
			~~neighbor EVPN-OVERLAY-PEERS activate
		~!
		~address-family ipv4
			~~no neighbor EVPN-OVERLAY-PEERS activate
			~~network {lo0}/32
		~!
		@{role=spine}
		
		@
		~neighbor EVPN-OVERLAY-PEERS peer-group
		~neighbor EVPN-OVERLAY-PEERS remote-as {spine_asn}
		~neighbor EVPN-OVERLAY-PEERS update-source Loopback0
		~neighbor EVPN-OVERLAY-PEERS allowas-in 5
		~neighbor EVPN-OVERLAY-PEERS ebgp-multihop 5
		~neighbor EVPN-OVERLAY-PEERS send-community extended
		~neighbor EVPN-OVERLAY-PEERS maximum-routes 12000 
		~neighbor IPv4-UNDERLAY-PEERS peer-group
		~neighbor IPv4-UNDERLAY-PEERS remote-as {spine_asn}
		~neighbor IPv4-UNDERLAY-PEERS allowas-in 1
		~neighbor IPv4-UNDERLAY-PEERS send-community
		~neighbor IPv4-UNDERLAY-PEERS maximum-routes 12000
		
		[~neighbor {spine_lo0_list} peer-group EVPN-OVERLAY-PEERS
		~neighbor {spine_ipv4_list} peer-group IPv4-UNDERLAY-PEERS
		~neighbor {spine_ipv4_list} description TO-{spine_hostname_list}]
		
		~address-family evpn
			~~neighbor EVPN-OVERLAY-PEERS activate
		~!
		~address-family ipv4
			~~no neighbor EVPN-OVERLAY-PEERS activate
			~~network {lo0}/32
			~~network {lo1}/32
		~!
		@{role=leaf}
		
		@
		~neighbor {mlag_peer_address} remote-as {asn}
		~neighbor {mlag_peer_address} next-hop-self
		~neighbor {mlag_peer_address} allowas-in 1
		~neighbor {mlag_peer_address} maximum-routes 12000
		@{role=leaf|mlag_neighbor}
		
		
		@
		[~vrf {vrf_name}
			~~rd {lo0}:{ibgp_vlan}
			~~route-target import 1000:{ibgp_vlan}
			~~route-target export 1000:{ibgp_vlan}
			~~neighbor {ibgp_peer_address} remote-as {asn}
			~~neighbor {ibgp_peer_address} next-hop-self
			~~neighbor {ibgp_peer_address} update-source Vlan{ibgp_vlan}
			~~neighbor {ibgp_peer_address} allowas-in 1
			~~neighbor {ibgp_peer_address} maximum-routes 12000 
			~~redistribute connected
		~!]
		@{role=leaf}
```

The only things we are not familiar with yet is the repetitive use of the ~ (tilde), the configuration template text does not respect whitespace, therefore no matter how we format, the lines ignore tabs and spaces.
Each tilde is converted into a tab upon compilation.

One other thing to note is the section tests support multiple tests and support comparison checks i.e. ```{role=leaf|mlag_neighbor}``` will pass if role indeed equals leaf and mlag_neighbor resolves to a value.
If these tests fail the whole section is pruned.



So far we have operated in day1 which compiles each template per device found in the fabric_parameters.csv.
It is important to differentiate what happens internally when we switch to day2 mode of operation.
We saw that whatever columns were defined in the fabric_parameters.csv file became available as "variables" within the templates.
Once we switch to day2, the CSV is ignored and the devices for which each template is compiled for are instead pulled from the CVP inventory.

But what variables are available in day2 operation since we are not using fabric_parameters.csv?
In day2 mode of operation, the parser implements Arista's CVPRAC Python library to communicate with CVP.
i.e. the get_inventory method is used to load device instances.

The data returned is:

```
>python
>>>import builder
>>>import json
>>>builder.debug()
Tue Nov 19 10:49:48 2019: Successfully authenticated to CVP
>>>print json.dumps(builder.CVP.cvprac.api.get_inventory(), indent=4)
[
    {
        "memTotal": 0,
        "version": "4.20.11M",
        "internalVersion": "4.20.11M",
        "dcaKey": null,
        "systemMacAddress": "52:54:00:9b:e5:8e",
        "tempAction": null,
        "deviceStatus": "Registered",
        "taskIdList": [],
        "internalBuildId": "107ed632-2ade-481f-afb4-86f6991f46a5",
        "mlagEnabled": false,
        "modelName": "vEOS",
        "hostname": "sw-10.20.30.66",
        "complianceCode": "",
        "danzEnabled": false,
        "type": "netelement",
        "isDANZEnabled": false,
        "parentContainerId": "undefined_container",
        "status": "Registered",
        "unAuthorized": false,
        "parentContainerKey": "undefined_container",
        "deviceInfo": "Registered",
        "ztpMode": true,
        "bootupTimestamp": 1574161796.800534,
        "lastSyncUp": 0,
        "key": "52:54:00:9b:e5:8e",
        "containerName": "Undefined",
        "sslConfigAvailable": false,
        "domainName": "",
        "internalBuild": "107ed632-2ade-481f-afb4-86f6991f46a5",
        "sslEnabledByCVP": false,
        "serialNumber": "21AB53275C2FA78E1D786A010468E22C",
        "fqdn": "sw-10.20.30.66",
        "bootupTimeStamp": 1574161796.800534,
        "isMLAGEnabled": false,
        "streamingStatus": "active",
        "memFree": 0,
        "architecture": "",
        "hardwareRevision": "",
        "ipAddress": "10.20.30.66",
        "complianceIndication": ""
    },
    {
        "memTotal": 0,
        "version": "4.23.0F",
        "internalVersion": "4.23.0F",
        "dcaKey": null,
        "systemMacAddress": "00:1c:73:74:83:88",
        "tempAction": null,
        "deviceStatus": "Registered",
        "taskIdList": [],
        "internalBuildId": "158ef907-fbb0-49af-950b-a2a8e86f3d07",
        "mlagEnabled": false,
        "modelName": "DCS-7050TX-96",
        "hostname": "DC1-LF10-MSS",
        "complianceCode": "0009",
        "danzEnabled": false,
        "type": "netelement",
        "isDANZEnabled": false,
        "parentContainerId": "container_127_9848052469563400",
        "status": "Registered",
        "unAuthorized": false,
        "parentContainerKey": "container_127_9848052469563400",
        "deviceInfo": "Registered",
        "ztpMode": false,
        "bootupTimestamp": 1570481564.230786,
        "lastSyncUp": 0,
        "key": "00:1c:73:74:83:88",
        "containerName": "DC1-Leaf",
        "sslConfigAvailable": false,
        "domainName": "lab.local",
        "internalBuild": "158ef907-fbb0-49af-950b-a2a8e86f3d07",
        "sslEnabledByCVP": false,
        "serialNumber": "JAS14270029",
        "fqdn": "DC1-LF10-MSS.lab.local",
        "bootupTimeStamp": 1570481564.230786,
        "isMLAGEnabled": false,
        "streamingStatus": "active",
        "memFree": 0,
        "architecture": "i386",
        "hardwareRevision": "00.01",
        "ipAddress": "10.20.30.32",
        "complianceIndication": "WARNING"
    }...
 ```
 
This is the data which becomes automatically available per device when in day2 mode. However, when operating in day2 mode we are usually interested in creating configlets based more on external data over individual switch data.
Hence, in day1 mode of operation we are interested in the CSV variables, and we use them, however, not so much for day1, but the data is there, and this is what is available.
 
So in day2 we need to specify the ```compile_for``` list in the recipe which controls which devices we will compile for.
e.g.
 
```
compile_for = [JAS16420034|DC1-LF07]
```
 
Assign_to, if defined will assign the configlets to the specified devices; if left blank or removed all-together consider compile_for = assign_to.
 
```
assign_to = 
```
 
compile_for/assign_to is always defined as a list and accepts container names, serial numbers, or hostnames. These are the devices for which compilation will take place.
There is a setting ```follow_child_containers``` which controls the behavior for specified containers, you can either return immediate switches in the container or follow the hierarchy and return all devices if child containers exist.
 
There is also an option to make the template a ```singleton```; i.e. we want a global configlet which can be assigned to devices or containers.
If ```singleton = True``` then compile_for is ignored and assign_to will treat containers/devices as single nodes where to assign the singleton configlet.
 
If a configlet is a singleton we wouldn't care about multiple devices so expanding containers makes no sense.

In day2 mode we want to differentiate spines and leafs so either in the global or recipe config we HAVE to define the spines/leafs.
e.g. 

```
spines = [HSH14085036|JPE18372884]
leafs = []
```

If we want the distinction between spines and leafs the above is required. Internally the above will assign the role variable to either "spine" or "leaf".
So the role variable will always exist in day1 or day2 operations where it is defined in the CSV or in the above lists respective of the mode.




As another example let's build a template which maps VLAN's to VNI's.

1. Create exampleFilename.csv with the headers ```vlan, description```.

```
vlan,description
10,vlan 10
20,vlan 20
30,vlan 30
```

2. Create the template definition for vlan-to-vni in templates.conf

```
[vlan2vni]
basetemplate =
	
	router bgp {/Sysdb/routing/bgp/config#asNumber}
	 	[~vlan {exampleFilename#vlan}
	 		~~rd {/Sysdb/ip/config/ipIntfConfig/Loopback0#addrWithMask(:-3)}:{exampleFilename#vlan*10}
	 		~~route-target both {exampleFilename#vlan*10}:{exampleFilename#vlan*10}
	 		~~redistribute learned
	 	~!]
	!
	interface Vxlan1
		[~vxlan vlan {exampleFilename#vlan} vni {exampleFilename#vlan*10}]
	!
	[vlan {exampleFilename#vlan}
		~name {exampleFilename#description}
	!]
```

2. Add the user-defined section in global.conf

```
[vlan-to-vni]
recipe = [vlan2vni]
```



On deployment:

```
>python builder.py
>(Cmd) deploy vlan-to-vni
```

Output:
```
**************************************************
VLAN2VNI-DC1-SP01-CONFIG
**************************************************
router bgp 65001
	vlan 10
		rd 10.0.1.1/32:100
		route-target both 100:100
		redistribute learned
	!
	vlan 20
		rd 10.0.1.1/32:200
		route-target both 200:200
		redistribute learned
	!
	vlan 30
		rd 10.0.1.1/32:300
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
**************************************************
```

We injected external CSV filenames and iterated on their values. Anything separated by a \# e.g. ```{filename#column}``` will try to open filename.csv and read that column.
We specified telemetry endpoints and extracted the ```asNumber``` and ```Loopback0:addrWithMask(:-3)``` from the CVP telemetry database for the device. Anything separated with a \# but starting with a forward slash will try to hit the telemetry API endpoint and extract the requested key.
Notice the truncation syntax is exactly as Python's syntax except we use brackets.
Math and Truncation cannot be used together; this can be but is not supported as of now.
