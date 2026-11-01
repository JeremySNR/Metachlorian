"""Exercise the shipped Lua handler, not a Python reimplementation of it."""
import hashlib
from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).parents[1]/'metachlorian/photos/lightroom/MetachlorianPhotos.lrplugin'


@pytest.fixture
def lua():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.globals().digest = lambda value: hashlib.md5(value.encode()).hexdigest()
    vm.globals()._PLUGIN = vm.table(path=str(ROOT))
    vm.execute('package.path = ... .. "/?.lua;" .. package.path', str(ROOT))
    vm.execute((Path(__file__).parent/'fixtures/photo_lightroom_sdk.lua').read_text())
    return vm


def test_shipped_files_compile_in_lightroom_lua_version():
    vm = LuaRuntime()
    compile = vm.eval('function(s) local f,e = loadstring(s); assert(f,e) end')
    for path in ROOT.glob('*.lua'):
        compile(path.read_text())


def test_lightroom_14_2_uses_available_controls_and_gates_masks(lua):
    lua.execute('''
        fixture.version = {major=14, minor=2}
        local status = handler.status()
        assert(status.connector_version == '0.2.0' and status.features.find_by_path)
        assert(status.capabilities.editing)
        local caps = context().capabilities
        assert(caps.controls.Exposure2012 and not caps.controls.PointColor)
        assert(#caps.mask_types == 0)
        local out = handler.apply(request('lr142', {{op='settings',values={Exposure2012=-0.3,CropLeft=0.1}}}))
        assert(out.photo.settings.Exposure2012 == -0.3 and out.photo.settings.CropLeft == 0.1)
        local writes = fixture.writes
        local ok, err = pcall(handler.apply, request('mask142', {{op='mask',type='subject',adjustments={local_Exposure=0.2}}}))
        assert(not ok and tostring(err):find('unavailable'))
        assert(fixture.writes == writes)
        fixture.version = {major=14, minor=1}
        assert(not context().capabilities.editing and context().capabilities.reason)
    ''')


def test_lookup_matches_master_without_import_or_edit(lua):
    lua.execute('''
        photo.virtual = false
        local result = handler.findPhoto({catalog_uid='catalog',path='/pictures/family.raw'})
        assert(result.photo.lr_id == '1' and result.photo.settings.Exposure2012 == 0)
        assert(handler.findPhoto({catalog_uid='catalog',path='/pictures/absent.raw'}).photo == nil)
        assert(not pcall(handler.findPhoto, {catalog_uid='different',path='/pictures/family.raw'}))
        assert(fixture.writes == 0 and #photo.snapshots == 0)
    ''')


def test_handler_apply_readback_receipt_and_human_conflict(lua):
    lua.execute('''
        local args = request('edit1', {{op='settings', values={Exposure2012=0.35}}})
        local out = handler.apply(args)
        assert(out.photo.settings.Exposure2012 == 0.35)
        assert(out.snapshot_id and out.recovery_snapshot)
        assert(handler.apply(args).photo.revision == out.photo.revision)
        assert(fixture.writes == 1)
        photo.settings.Exposure2012 = 0.8
        local ok, err = pcall(handler.apply, args)
        assert(not ok and tostring(err):find('CONFLICT:'))
        assert(fixture.writes == 1)
    ''')


def test_handler_partial_failure_is_not_replayed_and_has_recovery(lua):
    lua.execute('''
        fixture.failMask = true
        local args = request('edit2', {
            {op='settings', values={Exposure2012=0.4}},
            {op='mask', type='subject', adjustments={local_Exposure=0.2}},
        })
        local ok, err = pcall(handler.apply, args)
        assert(not ok and tostring(err):find('recovery snapshot:'))
        assert(fixture.writes == 1)
        ok, err = pcall(handler.apply, args)
        assert(not ok and tostring(err):find('interrupted operation'))
        assert(fixture.writes == 1)
        local ctx = context()
        assert(#ctx.recovery_snapshots == 1)
        local restored = handler.restore({ catalog_uid='catalog', photo_id='1', session_id='peabc',
            expected_revision=ctx.photo.revision, snapshot_id=ctx.recovery_snapshots[1].id, operation_id='restore1' })
        assert(restored.photo.settings.Exposure2012 == 0)
    ''')


def test_handler_validates_entire_request_before_mutation(lua):
    lua.execute('''
        for _, values in ipairs({{Exposure2012=6}, {Unrecognised=1}, {CropLeft=0.9,CropRight=0.2},
            {WhiteBalance='invalid'}, {ToneCurvePV2012={100,0,50,255}}}) do
            local ok = pcall(handler.apply, request('invalid', {{op='settings', values=values}}))
            assert(not ok)
        end
        assert(fixture.writes == 0 and #photo.snapshots == 0)
        photo.settings.Temperature = 0
        photo.settings.Tint = 0
        assert(context().capabilities.controls.Temperature.min == -100)
        assert(context().capabilities.controls.Tint.min == -100)
        photo.virtual = false
        assert(not pcall(handler.apply, request('master', {{op='settings', values={Exposure2012=0.2}}})))
        photo.virtual = true
        fixture.version.major = 16
        assert(context().capabilities.editing == false)
        assert(not pcall(handler.apply, request('future', {{op='settings', values={Exposure2012=0.2}}})))
    ''')


def test_plugin_panel_requires_authenticated_traffic_and_can_refresh():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('package.path = ... .. "/?.lua;" .. package.path', str(ROOT))
    vm.execute('''
        local realRequire = require
        local prefs = {}
        local imports = {
            LrApplication = {versionTable=function() return {major=14,minor=2} end},
            LrPrefs = {prefsForPlugin=function() return prefs end},
            LrView = {bind=function(key) return key end},
        }
        function import(name) return imports[name] or {} end
        function require(name)
            if name == 'Log' then return {info=function() end,filePath=function() return '/tmp/connector.log' end} end
            if name == 'HandlerMetachlorian' then return {dispatch={}} end
            return realRequire(name)
        end
        local provider = require 'PluginInfoProvider'
        assert(provider.connectionSummary():find('Connection stopped',1,true))
        local state = MetachlorianPhotos_State
        state.running, state.receiveConnected, state.sendConnected = true, true, true
        assert(provider.connectionSummary():find('Waiting for Metachlorian',1,true))
        state.lastAuthenticatedAt, state.lastAction = os.time(), 'mc_status'
        assert(provider.connectionSummary():find('Metachlorian connected',1,true))
        local observers = {}
        local props = {addObserver=function(_,key,fn) observers[key]=fn end}
        local f = setmetatable({}, {__index=function() return function(_,options) return options end end})
        local sections = provider.sectionsForTopOfDialog(f, props)
        assert(props.connectionSummary:find('Lightroom Classic 14.2',1,true))
        assert(props.requestPort == 58773 and props.responsePort == 58774)
        observers.requestPort(nil,nil,59001); observers.responsePort(nil,nil,59002)
        assert(prefs.requestPort == 59001 and prefs.responsePort == 59002)
        state.sendConnected = false
        sections[1][3][3].action() -- Refresh status bound to the panel.
        assert(props.connectionSummary:find('Waiting for Metachlorian',1,true))
        provider.resetForReload()
        assert(not state.lastAuthenticatedAt and not state.lastAction)
    ''')
