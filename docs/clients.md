# Using the client with Patchcord

By default, Patchcord loads the latest Canary client on any url that isn't an explicit route or on `/api`.

However, it has the capability of loading any build either in the (discord.sale)[https://discord.sale] API or `/assets/builds.json`.
You can change the default client to any build in the config, or manually launch a seperate client.

## Loading other builds
Builds can be loaded in two ways:

1. Launching directly
You can navigate to `/launch/<hash>` or `/build/<hash>` to load a specific build hash. "latest" is a valid hash if you want to load the latest client. You can also navigate to `/launch` or `/build` for the latest build.

2. Build overrides
Patchcord repurposes the build override system for loading Discord builds. This currently requires the staff flag (subject to change). Additionally, build overrides specified, again, in `/assets/builds.json` can also be loaded this way. As the whole system is based on build overrides, method 1 above also implicitly creates a build override. This allows for easily going back to the default client by just clearing the override.
