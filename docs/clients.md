# Clients that can work with Litecord

 - [koneko](https://gitlab.com/luna/koneko)
 - [crcophony](https://github.com/freyamade/crcophony), edit
    `lib/discordcr/src/discordcr/rest.cr`'s `Discord::REST::API_BASE`. Not
    settable at runtime.
 - [discord-term](https://github.com/cloudrex/discord-term), with manual edits
```diff
diff --git a/src/display.ts b/src/display.ts
index e844553..9e8521a 100644
--- a/src/display.ts
+++ b/src/display.ts
@@ -205,7 +205,15 @@ export default class Display {
             ...state
         };

-        this.client = new Client;
+        this.client = new Client({
+            http: {
+                host: 'https://INSTANCE_URL_HERE',
+                cdn: 'https://INSTANCE_URL_HERE',
+                version: 6
+            },
+            fetchAllMembers: true,
+            sync: true
+        });
         this.commands = commands;
     }
```

## Clients known to not work with litecord

Clients built on libraries that do not have an easy way to edit the base URL are
not suited for Litecord.

