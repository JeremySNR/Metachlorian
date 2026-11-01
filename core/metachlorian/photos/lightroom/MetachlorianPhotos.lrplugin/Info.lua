return {
    LrSdkVersion = 8.0,
    LrSdkMinimumVersion = 8.0,

    LrToolkitIdentifier = 'com.metachlorian.photos',
    LrPluginName = "Metachlorian Photos",

    LrPluginInfoUrl = "https://github.com/JeremySNR/Metachlorian",

    VERSION = { major=0, minor=2, revision=0, build=0 },

    LrPluginInfoProvider = 'PluginInfoProvider.lua',
    LrInitPlugin = 'PluginInit.lua',
    LrMetadataProvider = 'MetachlorianMetadata.lua',
    -- LrForceInitPlugin forces eager load on Lr launch, but ONLY if the
    -- plugin also exposes at least one menu item — see LrLibraryMenuItems
    -- below. Adobe's own remote_control_socket sample uses this pattern.
    LrForceInitPlugin = true,

    LrLibraryMenuItems = {
        {
            title = "Metachlorian Photos — Show Status",
            file = "MenuShowStatus.lua",
        },
    },
}
