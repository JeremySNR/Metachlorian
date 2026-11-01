-- The only externally dispatched catalogue operations. Upstream's raw write,
-- delete, undo and undocumented-mask handlers are intentionally unreachable.
local LrApplication = import 'LrApplication'
local LrDevelopController = import 'LrDevelopController'
local LrFileUtils = import 'LrFileUtils'
local LrPathUtils = import 'LrPathUtils'
local LrUUID = import 'LrUUID'
local LrMD5 = import 'LrMD5'
local LrTasks = import 'LrTasks'
local LrExportSession = import 'LrExportSession'
local JSON = require 'JSON'
local PhotoLookup = require 'PhotoLookup'
local Metadata = require 'HandlerMetadata'
local Preview = require 'HandlerPreview'
local Copies = require 'HandlerVirtualCopies'
local Snapshots = require 'HandlerSnapshots'
local Masks = require 'HandlerMaskCreate'
local DevelopSession = require 'DevelopSession'

local Handler = {}
local controlsFile = assert(io.open(LrPathUtils.child(_PLUGIN.path, 'controls.json'), 'r'))
local CONTROL_SPECS = JSON:decode(controlsFile:read('*a'))
controlsFile:close()
local scan = nil
local busy = false

local function canonical(value)
    if type(value) ~= 'table' then return JSON:encode(value) end
    local keys, values = {}, {}
    for key in pairs(value) do keys[#keys + 1] = key end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, key in ipairs(keys) do
        values[#values + 1] = JSON:encode(tostring(key)) .. ':' .. canonical(value[key])
    end
    return '{' .. table.concat(values, ',') .. '}'
end

local function revision(photo)
    return LrMD5.digest(canonical(photo:getDevelopSettings()))
end

local function raw(photo, key)
    local ok, value = LrTasks.pcall(function() return photo:getRawMetadata(key) end)
    if ok then return value end
end

local function catalogInfo()
    local catalog = LrApplication.activeCatalog()
    local uid = catalog:getPropertyForPlugin(_PLUGIN, 'catalogUid')
    if not uid then
        catalog:withWriteAccessDo('Connect Metachlorian', function()
            uid = catalog:getPropertyForPlugin(_PLUGIN, 'catalogUid') or LrUUID.generateUUID()
            catalog:setPropertyForPlugin(_PLUGIN, 'catalogUid', uid)
        end)
    end
    local version = LrApplication.versionTable()
    return catalog, { uid = uid, path = catalog:getPath(), name = LrPathUtils.leafName(catalog:getPath()),
        version = tostring(version.major) .. '.' .. tostring(version.minor) }
end

local function resolve(args)
    local catalog, info = catalogInfo()
    if args.catalog_uid ~= info.uid then error('CONFLICT: The active Lightroom catalogue changed') end
    local photo = PhotoLookup.resolveOne(catalog, args.photo_id)
    if not photo then error('Photo is no longer in the active catalogue') end
    return catalog, photo, info
end

local function describe(photo, includeSettings)
    local out = Metadata.getPhotoMetadata({ photo_id = tostring(photo.localIdentifier) })
    out.lr_id = tostring(photo.localIdentifier)
    out.path = raw(photo, 'path')
    out.filename = LrPathUtils.leafName(out.path)
    out.capture_time = raw(photo, 'dateTimeOriginalISO8601')
    out.last_edit_time = raw(photo, 'lastEditTime')
    out.dimensions = raw(photo, 'dimensions')
    out.cropped_dimensions = raw(photo, 'croppedDimensions')
    out.orientation = raw(photo, 'orientation')
    out.is_virtual = raw(photo, 'isVirtualCopy') == true
    out.copy_name = raw(photo, 'copyName') or ''
    local master = out.is_virtual and raw(photo, 'masterPhoto') or nil
    out.master_lr_id = master and tostring(master.localIdentifier) or nil
    local smart = raw(photo, 'smartPreviewInfo')
    out.availability = LrFileUtils.exists(out.path) == 'file' and 'original'
        or (type(smart) == 'table' and smart.smartPreviewPath and 'smart_preview' or 'cached_preview_only')
    if includeSettings then
        out.revision = revision(photo)
        local settings = photo:getDevelopSettings()
        out.settings = {}
        for key in pairs(CONTROL_SPECS) do out.settings[key] = settings[key] end
        out.process_version = settings.ProcessVersion
    else
        -- A lightweight sync marker. Exact revision is read before any write
        -- or freshly requested rendition, not serialised for 100k mask tables.
        out.revision = tostring(out.last_edit_time or '')
    end
    return out
end

local function capabilities(photo)
    local settings = photo and photo:getDevelopSettings() or {}
    local available = {}
    for key, spec in pairs(CONTROL_SPECS) do
        if settings[key] ~= nil then available[key] = spec end
    end
    if available.Temperature and tonumber(settings.Temperature) and settings.Temperature < 1000 then
        available.Temperature = { type = 'number', min = -100, max = 100, family = 'white_balance', units = 'relative' }
        if available.Tint then available.Tint = { type = 'number', min = -100, max = 100, family = 'white_balance', units = 'relative' } end
    end
    local version = LrApplication.versionTable()
    local major, minor = tonumber(version.major), tonumber(version.minor)
    local supported = (major == 14 and minor and minor >= 2) or (major == 15 and minor and minor <= 6)
    if photo and (type(photo.getDevelopSettings) ~= 'function' or type(photo.applyDevelopSettings) ~= 'function') then supported = false end
    local reason = not supported and 'This connector supports Lightroom Classic 14.2–15.6 with per-photo control checks. This version or photo does not expose the required develop API.' or nil
    local masks = {}
    -- Mask automation stays on the narrower adapter target; basic develop
    -- settings, virtual copies, snapshots and exports use the older public SDK.
    if supported and major == 15 and minor == 6 and type(LrDevelopController.createNewMask) == 'function' then
        masks = { 'subject', 'sky', 'background' }
    end
    return { controls = supported and available or {}, mask_types = masks,
        auto = supported and type(LrDevelopController.setAutoTone) == 'function' and type(LrDevelopController.setAutoWhiteBalance) == 'function',
        editing = supported == true, reason = reason, supported_versions = '14.2–15.6', certification = 'pending_live_validation',
        unsupported = { 'point_color', 'people_masks', 'range_masks', 'gradient_geometry', 'generative_remove',
            'lens_blur', 'enhance', 'hdr_merge', 'panorama', 'hdr_output' },
        coordinate_space = 'oriented_render', raw_recovery_known = false }
end

local function checkRevision(photo, expected)
    if type(expected) ~= 'string' or expected == '' or revision(photo) ~= expected then
        error('CONFLICT: Develop settings changed. Inspect the current edit before continuing.')
    end
end

local function owned(photo, sessionId)
    if not raw(photo, 'isVirtualCopy') or photo:getPropertyForPlugin(_PLUGIN, 'sessionId') ~= sessionId then
        error('This operation requires a virtual copy owned by this edit session')
    end
end

local function receipt(photo, operationId)
    local encoded = photo:getPropertyForPlugin(_PLUGIN, 'receipt')
    if not encoded then return nil end
    local ok, value = pcall(function() return JSON:decode(encoded) end)
    if ok and value.operation_id == operationId then return value end
    if ok and value.entries then return value.entries[operationId] end
end

local function saveReceipt(catalog, photo, operationId, result)
    catalog:withWriteAccessDo('Record Metachlorian edit', function()
        local journal = { entries = {}, order = {} }
        local encoded = photo:getPropertyForPlugin(_PLUGIN, 'receipt')
        if encoded then
            local ok, decoded = pcall(function() return JSON:decode(encoded) end)
            if ok and decoded.entries then journal = decoded end
        end
        if not journal.entries[operationId] then journal.order[#journal.order + 1] = operationId end
        journal.entries[operationId] = { operation_id = operationId, result = result }
        while #journal.order > 32 do journal.entries[table.remove(journal.order, 1)] = nil end
        photo:setPropertyForPlugin(_PLUGIN, 'receipt', JSON:encode(journal))
    end)
end

local function replay(photo, operationId)
    if type(operationId) ~= 'string' or #operationId == 0 or #operationId > 200 then error('Invalid operation ID') end
    local prior = receipt(photo, operationId)
    if not prior then return nil end
    if prior.result.incomplete then
        error('CONFLICT: An interrupted operation needs inspection; recovery snapshot: ' .. tostring(prior.result.recovery_snapshot))
    end
    -- An old receipt must never conceal subsequent human changes.
    checkRevision(photo, prior.result.photo.revision)
    return prior.result
end

local function snapshot(photo, name)
    for _, snap in ipairs(photo:getDevelopSnapshots() or {}) do
        if snap.name == name then return tostring(snap.snapshotID) end
    end
    return Snapshots.create({ photo_id = tostring(photo.localIdentifier), name = name }).snapshot.id
end

function Handler.status()
    local _, info = catalogInfo()
    return { protocol = 1, connector_version = '0.2.0', features = { find_by_path = true },
        catalog = info, capabilities = capabilities(nil) }
end

function Handler.findPhoto(args)
    local catalog, info = catalogInfo()
    if args.catalog_uid ~= info.uid then error('CONFLICT: Catalogue changed while matching a file') end
    if type(args.path) ~= 'string' or #args.path == 0 then error('A file path is required') end
    local photo = catalog:findPhotoByPath(args.path)
    if photo and raw(photo, 'isVirtualCopy') then photo = raw(photo, 'masterPhoto') end
    return { catalog = info, photo = photo and describe(photo, true) or nil }
end

function Handler.catalogPage(args)
    local catalog, info = catalogInfo()
    if args.catalog_uid and args.catalog_uid ~= info.uid then error('CONFLICT: Catalogue changed during synchronisation') end
    local cursor = tonumber(args.cursor) or 0
    local limit = math.max(1, math.min(100, tonumber(args.limit) or 100))
    if cursor == 0 or not scan or scan.uid ~= info.uid then
        scan = { uid = info.uid, photos = catalog:getAllPhotos() }
        table.sort(scan.photos, function(a, b) return a.localIdentifier < b.localIdentifier end)
    end
    local output = {}
    for i = cursor + 1, math.min(cursor + limit, #scan.photos) do
        local photo = scan.photos[i]
        if raw(photo, 'fileFormat') ~= 'VIDEO' then output[#output + 1] = describe(photo, false) end
        if i % 10 == 0 then LrTasks.yield() end
    end
    local nextCursor = math.min(cursor + limit, #scan.photos)
    return { catalog = info, photos = output, total = #scan.photos,
        cursor = nextCursor, complete = nextCursor >= #scan.photos }
end

function Handler.context(args)
    local _, photo, info = resolve(args)
    local recovery = {}
    for _, snap in ipairs(photo:getDevelopSnapshots() or {}) do
        if snap.name:match('^pe[%w]+ ') then recovery[#recovery + 1] = { id = tostring(snap.snapshotID), name = snap.name } end
    end
    return { catalog = info, photo = describe(photo, true), capabilities = capabilities(photo), recovery_snapshots = recovery }
end

function Handler.preview(args)
    local _, photo = resolve(args)
    local result = Preview.getPhotoPreview({ photo_id = tostring(photo.localIdentifier), size = args.size or 1024 })
    result.revision = revision(photo)
    result.source = describe(photo, false).availability
    return result
end

function Handler.render(args)
    local _, photo = resolve(args)
    checkRevision(photo, args.expected_revision)
    local availability = describe(photo, false).availability
    if availability == 'cached_preview_only' then error('Original or Smart Preview required to render a fresh edit') end
    if args.native and availability ~= 'original' then error('Original required for native-resolution focus inspection') end
    if type(args.destination) ~= 'string' or not args.destination:find('scratch%-') or args.destination:find('%.%.[/\\]') then
        error('A reserved Metachlorian scratch directory is required')
    end
    local settings = {
        LR_export_destinationType = 'specificFolder', LR_export_destinationPathPrefix = args.destination,
        LR_export_useSubfolder = false, LR_collisionHandling = 'overwrite', LR_format = 'JPEG',
        LR_jpeg_quality = 0.9, LR_export_colorSpace = 'sRGB', LR_outputSharpeningOn = false,
        LR_minimizeEmbeddedMetadata = true, LR_removeLocationMetadata = true,
        LR_size_doConstrain = not args.native, LR_size_resizeType = 'longEdge',
        LR_size_maxWidth = math.min(2048, args.size or 1600), LR_size_maxHeight = math.min(2048, args.size or 1600),
        LR_size_doNotEnlarge = true,
    }
    local session = LrExportSession { photosToExport = { photo }, exportSettings = settings }
    local path
    for _, rendition in session:renditions { stopIfCanceled = true } do
        local ok, result = rendition:waitForRender()
        if not ok then error('Lightroom render failed: ' .. tostring(result)) end
        path = result
    end
    checkRevision(photo, args.expected_revision)
    return { path = path, revision = args.expected_revision, source = availability, native_resolution = args.native == true }
end

function Handler.begin(args)
    local catalog, photo = resolve(args)
    if not capabilities(photo).editing then error(capabilities(photo).reason) end
    if type(args.session_id) ~= 'string' or not args.session_id:match('^pe[%w]+$') then error('Invalid edit session') end
    local copyName = 'Metachlorian ' .. args.session_id
    local master = raw(photo, 'isVirtualCopy') and raw(photo, 'masterPhoto') or photo
    local copy
    -- Copy name is set by createVirtualCopies itself: a lost response between
    -- creation and adding custom metadata cannot create a duplicate on retry.
    for _, candidate in ipairs(raw(master, 'virtualCopies') or {}) do
        if raw(candidate, 'copyName') == copyName then copy = candidate break end
    end
    if not copy then
        checkRevision(photo, args.expected_revision)
        local made = Copies.create({ photo_ids = { tostring(photo.localIdentifier) }, copy_name = copyName })
        copy = PhotoLookup.resolveOne(catalog, made.copies[1].copy_id)
    end
    catalog:withWriteAccessDo('Own Metachlorian virtual copy', function()
        copy:setPropertyForPlugin(_PLUGIN, 'sessionId', args.session_id)
    end)
    local snapshotName = args.session_id .. ' baseline'
    local baseline = snapshot(copy, snapshotName)
    return { photo = describe(copy, true), baseline_snapshot = baseline }
end

local function validateValues(values, specs)
    if type(values) ~= 'table' then error('Settings must be an object') end
    for key, value in pairs(values) do
        local spec = specs[key]
        if not spec then error('Unsupported Lightroom setting: ' .. tostring(key)) end
        if spec.type == 'number' and (type(value) ~= 'number' or value ~= value or value < spec.min or value > spec.max) then error('Invalid value for ' .. key) end
        if spec.type == 'boolean' and type(value) ~= 'boolean' then error('Invalid boolean for ' .. key) end
        if spec.type == 'string' and (type(value) ~= 'string' or #value > 200) then error('Invalid string for ' .. key) end
        if spec.type == 'enum' then
            local valid = false
            for _, allowed in ipairs(spec.values) do if value == allowed then valid = true end end
            if not valid then error('Invalid choice for ' .. key) end
        end
        if spec.type == 'curve' then
            if type(value) ~= 'table' or #value < 4 or #value > 64 or #value % 2 ~= 0 then error('Invalid curve') end
            for i, point in ipairs(value) do
                if type(point) ~= 'number' or point ~= point or point < 0 or point > 255 then error('Invalid curve point') end
                if i % 2 == 1 and i > 1 and point <= value[i - 2] then error('Curve x coordinates must increase') end
            end
        end
    end
end

function Handler.apply(args)
    local catalog, photo = resolve(args)
    owned(photo, args.session_id)
    local prior = replay(photo, args.operation_id)
    if prior then return prior end
    checkRevision(photo, args.expected_revision)
    local caps = capabilities(photo)
    if not caps.editing then error('This Lightroom version is not enabled for editing') end
    if type(args.operations) ~= 'table' or #args.operations < 1 or #args.operations > 12 then error('Invalid edit operations') end
    -- Validate before performing the first write.
    local combined = photo:getDevelopSettings()
    for _, operation in ipairs(args.operations) do
        if operation.op == 'settings' then
            validateValues(operation.values, caps.controls)
            for key, value in pairs(operation.values) do combined[key] = value end
        elseif operation.op == 'mask' then
            if #caps.mask_types == 0 then error('AI mask creation is unavailable in this Lightroom version; use supported global settings or a manual mask handoff') end
            if operation.type ~= 'subject' and operation.type ~= 'sky' and operation.type ~= 'background' then error('Unsupported mask') end
            local adjustments = {}
            for key, value in pairs(operation.adjustments or {}) do
                if not key:match('^local_') then error('Unsupported local adjustment') end
                local name = key:gsub('^local_', ''):lower()
                adjustments[name == 'luminancenoise' and 'noise' or name] = value
            end
            Masks.validateAdjustments(adjustments)
            Masks.requireCreateApi()
        elseif operation.op == 'auto' then
            if not caps.auto then error('Auto tone/white balance is unavailable in this Lightroom version') end
        else error('Unsupported edit operation') end
    end
    if (combined.CropLeft or 0) >= (combined.CropRight or 1) or (combined.CropTop or 0) >= (combined.CropBottom or 1) then error('Crop must have positive area') end
    local before = snapshot(photo, args.session_id .. ' before ' .. args.operation_id)
    saveReceipt(catalog, photo, args.operation_id, { incomplete = true, recovery_snapshot = before })
    local checkpoint = revision(photo)
    local ok, result = LrTasks.pcall(function()
        for _, operation in ipairs(args.operations) do
            checkRevision(photo, checkpoint)
            if operation.op == 'settings' then
                catalog:withWriteAccessDo('Metachlorian develop settings', function()
                    photo:applyDevelopSettings(operation.values, 'Metachlorian')
                end)
                local actual = photo:getDevelopSettings()
                for key, value in pairs(operation.values) do
                    if type(value) == 'number' then
                        local tolerance = key:match('^Crop') and 0.00001 or (key == 'Exposure2012' or key == 'SharpenRadius') and 0.01 or 0.51
                        if type(actual[key]) ~= 'number' or math.abs(actual[key] - value) > tolerance then error('Setting did not apply: ' .. key) end
                    elseif canonical(actual[key]) ~= canonical(value) then error('Setting did not apply: ' .. key) end
                end
            elseif operation.op == 'mask' then
                local adjustments = {}
                for key, value in pairs(operation.adjustments or {}) do
                    local name = key:gsub('^local_', ''):lower()
                    if name == 'luminancenoise' then name = 'noise' end
                    adjustments[name] = value
                end
                Masks.createMask({ photo_id = args.photo_id, type = operation.type, adjustments = adjustments })
            elseif operation.op == 'auto' then
                DevelopSession.withPhoto('Metachlorian Auto', catalog, photo, function()
                    if operation.tone then LrDevelopController.setAutoTone() end
                    if operation.white_balance then LrDevelopController.setAutoWhiteBalance() end
                    DevelopSession.flushPendingEdits()
                end)
            end
            checkpoint = revision(photo)
        end
        local snap = snapshot(photo, args.session_id .. ' candidate ' .. args.operation_id)
        return { photo = describe(photo, true), snapshot_id = snap, recovery_snapshot = before }
    end)
    if not ok then
        -- Preserve the recovery point. A partial failure is surfaced rather
        -- than globally undoing or overwriting possible human intervention.
        error('CONFLICT: ' .. tostring(result) .. '; recovery snapshot: ' .. before)
    end
    saveReceipt(catalog, photo, args.operation_id, result)
    return result
end

function Handler.restore(args)
    local catalog, photo = resolve(args)
    owned(photo, args.session_id)
    local prior = replay(photo, args.operation_id)
    if prior then return prior end
    checkRevision(photo, args.expected_revision)
    local valid = false
    for _, snap in ipairs(photo:getDevelopSnapshots() or {}) do
        if tostring(snap.snapshotID) == args.snapshot_id and snap.name:sub(1, #args.session_id) == args.session_id then valid = true end
    end
    if not valid then error('Snapshot does not belong to this edit session') end
    local before = snapshot(photo, args.session_id .. ' before ' .. args.operation_id)
    saveReceipt(catalog, photo, args.operation_id, { incomplete = true, recovery_snapshot = before })
    Snapshots.apply({ photo_id = args.photo_id, snapshot_id = args.snapshot_id })
    local result = { photo = describe(photo, true) }
    saveReceipt(catalog, photo, args.operation_id, result)
    return result
end

function Handler.finish(args)
    local catalog, photo = resolve(args)
    owned(photo, args.session_id)
    local prior = replay(photo, args.operation_id)
    if prior then return prior end
    checkRevision(photo, args.expected_revision)
    if type(args.collection) ~= 'string' or #args.collection == 0 or #args.collection > 200 then error('Invalid collection name') end
    local collection
    catalog:withWriteAccessDo('Save Metachlorian selection', function()
        local group = catalog:createCollectionSet('Metachlorian', nil, true)
        collection = catalog:createCollection(args.collection, group, true)
        collection:addPhotos({ photo })
    end)
    local result = { collection_id = tostring(collection.localIdentifier), photo = describe(photo, true) }
    saveReceipt(catalog, photo, args.operation_id, result)
    return result
end

function Handler.importPhoto(args)
    local catalog, info = catalogInfo()
    if args.catalog_uid ~= info.uid then error('CONFLICT: Catalogue changed') end
    if type(args.path) ~= 'string' or LrFileUtils.exists(args.path) ~= 'file' then error('Selected original is unavailable') end
    local photo = catalog:findPhotoByPath(args.path)
    if not photo then catalog:withWriteAccessDo('Add selected photo in place', function() photo = catalog:addPhoto(args.path) end) end
    return { catalog = info, photo = describe(photo, true) }
end

local function serial(fn)
    return function(args)
        if busy then error('Lightroom connector is busy; retry this job after the current operation') end
        busy = true
        local ok, result = LrTasks.pcall(fn, args or {})
        busy = false
        if not ok then error(result, 0) end
        return result
    end
end

Handler.dispatch = {
    ping = function() return { pong = true } end,
    mc_status = serial(Handler.status), mc_find_photo = serial(Handler.findPhoto), mc_catalog_page = serial(Handler.catalogPage),
    mc_context = serial(Handler.context), mc_preview = serial(Handler.preview), mc_render = serial(Handler.render),
    mc_begin = serial(Handler.begin), mc_apply = serial(Handler.apply), mc_restore = serial(Handler.restore),
    mc_finish = serial(Handler.finish), mc_import = serial(Handler.importPhoto),
}
return Handler
