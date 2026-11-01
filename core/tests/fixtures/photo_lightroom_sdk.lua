-- Minimal Adobe boundary for exercising our real handler in Lua 5.1.
-- This does not certify Adobe rendering or SDK behaviour on Mac/Windows.
local realRequire = require
local function copy(t)
    if type(t) ~= 'table' then return t end
    local out = {}; for k,v in pairs(t) do out[k] = copy(v) end; return out
end
fixture = { writes = 0, failMask = false, version = { major = 15, minor = 6 } }
photo = { localIdentifier = 1, settings = { Exposure2012 = 0, Temperature = 5500,
    CropLeft = 0, CropRight = 1, CropTop = 0, CropBottom = 1,
    ToneCurvePV2012 = {0,0,255,255}, WhiteBalance = 'Custom' },
    properties = { sessionId = 'peabc' }, snapshots = {}, virtual = true }
function photo:getDevelopSettings() return copy(self.settings) end
function photo:applyDevelopSettings(values)
    fixture.writes = fixture.writes + 1
    for k,v in pairs(values) do self.settings[k] = v end
end
function photo:getRawMetadata(key)
    local values = { path = '/pictures/family.raw', dimensions = { width = 6000, height = 4000 },
        lastEditTime = 123, isVirtualCopy = self.virtual, copyName = 'Metachlorian peabc' }
    return values[key]
end
function photo:getPropertyForPlugin(_, key) return self.properties[key] end
function photo:setPropertyForPlugin(_, key, value) self.properties[key] = value end
function photo:getDevelopSnapshots() return self.snapshots end
local catalog = {}
function catalog:getPropertyForPlugin() return 'catalog' end
function catalog:getPath() return '/pictures/Family.lrcat' end
function catalog:withWriteAccessDo(_, fn) return fn() end
local imports = {
    LrApplication = { activeCatalog = function() return catalog end, versionTable = function() return fixture.version end },
    LrTasks = { pcall = pcall, yield = function() end },
    LrMD5 = { digest = digest }, LrUUID = {}, LrExportSession = {},
    LrFileUtils = { exists = function() return 'file' end },
    LrPathUtils = { child = function(a,b) return a .. '/' .. b end, leafName = function(s) return s:match('[^/]+$') end },
    LrDevelopController = { createNewMask = function() end },
}
function import(name) return assert(imports[name], name) end
local mocks = {
    PhotoLookup = { resolveOne = function() return photo end },
    HandlerMetadata = { getPhotoMetadata = function() return { rating = 0, keywords = {} } end },
    HandlerPreview = {}, HandlerVirtualCopies = {},
    HandlerSnapshots = {
        create = function(args)
            local id = tostring(#photo.snapshots + 1)
            photo.snapshots[#photo.snapshots + 1] = { snapshotID = id, name = args.name, settings = copy(photo.settings) }
            return { snapshot = { id = id } }
        end,
        apply = function(args)
            photo.settings = copy(photo.snapshots[tonumber(args.snapshot_id)].settings)
        end,
    },
    HandlerMaskCreate = {
        validateAdjustments = function(values)
            for _,v in pairs(values) do assert(type(v) == 'number' and math.abs(v) <= 100, 'invalid local value') end
        end,
        requireCreateApi = function() end,
        createMask = function() if fixture.failMask then error('AI mask interrupted') end end,
    },
    DevelopSession = {},
}
function require(name) return mocks[name] or realRequire(name) end
handler = require 'HandlerMetachlorian'
function context() return handler.context({ catalog_uid = 'catalog', photo_id = '1' }) end
function request(id, operations, revision)
    return { catalog_uid = 'catalog', photo_id = '1', session_id = 'peabc',
        expected_revision = revision or context().photo.revision, operation_id = id, operations = operations }
end
