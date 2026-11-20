I would like to fix a few things in the laboratory because I have to remember the machines' addresses every time, and using names would be easier.
For example, there is [pc12], which I would like to reach by typing ai.research.lab.net, and [pc8] should also have the name shop.example.com. That should work from computers in other parts of the network too.
Oh, and there is [pc13], which I would like to find using data.research.lab.net, while for [pc9] I was thinking of api.service.com.
I also need to sort out the email for example.com: when someone sends email to that domain, I want them to find [pc4] using mail.example.com.
Anyway, I do not want to change the existing connections.
I almost forgot [pc11]: for that one I would like to use ci.tools.net. Then, for the email for lab.net, I would like to use mail.lab.net to find [pc6], and service.com should also have a machine that receives email, in this case [pc5] with the name mail.service.com.
Oh, and tools.net is missing: for that one too, I want email to go to [pc7], found using mail.tools.net.
I would like both email destinations to have the same priority, set to 10.
There is also something about how the names should be organized. I was thinking of starting from [pc1], then having two branches through [pc2] and [pc3].
From [pc2], I would like things to continue toward [pc4] and [pc5]. Then [pc4] should lead to [pc8], and [pc5] should lead to [pc9].
On the other side, [pc3] should lead to [pc6] and [pc7]. From [pc6], things should go through [pc10] and then split toward [pc12] and [pc13]. And from [pc7], I want to reach [pc11].
Oh, and when [pc16], [pc17], [pc18], [pc19], and [pc20] need to find a name, they should ask [pc14] to handle it.
I mean the organization of names, not adding new network connections or changing the ones already there.
In short, I want to use these names instead of addresses and find the machines from any computer in the laboratory, including the right machine when email needs to be sent to one of these domains.
Each machine should manage its own distinct part of the naming hierarchy.