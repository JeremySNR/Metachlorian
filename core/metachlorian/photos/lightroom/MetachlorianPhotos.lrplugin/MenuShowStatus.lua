local LrDialogs = import 'LrDialogs'
local provider = require 'PluginInfoProvider'
LrDialogs.message('Metachlorian Photos', provider.connectionSummary(), 'info')
