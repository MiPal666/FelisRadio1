import QtQuick 2.6
import Connman 0.2

// Read-only diagnostics. No connection requests, technology scans or setters.
Item {
    id: probe
    visible: false
    property bool diagnosticLogging: false
    property var previous: null
    signal observed(string reason)
    signal connectivityObserved(var state)
    signal castNetworkObserved(bool available, string key)
    function serviceState(service) {
        if (!service) return null
        var ethernet = service.ethernet || {}
        var ipv4 = service.ipv4 || {}
        return {type: service.type, state: service.state, connected: service.connected,
            error: service.error, interfaceName: ethernet.Interface || "",
            hasIpv4: !!ipv4.Address, ipv4Method: ipv4.Method || "",
            nameserverCount: (service.nameservers || []).length}
    }
    function snapshot(reason, force) {
        if (!manager || !wifi) return
        var current = {available: manager.available, valid: manager.valid,
            state: manager.state, connected: manager.connected, offlineMode: manager.offlineMode,
            connectingWifi: manager.connectingWifi,
            route: serviceState(manager.defaultRoute), wifi: serviceState(manager.connectedWifi),
            wifiAvailable: wifi.available, wifiPowered: wifi.powered, wifiConnected: wifi.connected}
        // Keep the service path (which can identify the Wi-Fi) out of logs.
        var service = manager.connectedWifi
        var castReady = manager.available && manager.valid && !manager.offlineMode && wifi.connected
                && service && service.connected && !!(service.ipv4 || {}).Address
                && (service.state === "ready" || service.state === "online")
        var castKey = castReady ? String(service.path || "wifi") + "|"
                + String((service.ethernet || {}).Interface || "") + "|" + String(service.ipv4.Address) : ""
        castNetworkObserved(!!castReady, castKey)
        if (!force && JSON.stringify(current) === JSON.stringify(previous)) return
        if (diagnosticLogging) console.warn("Felis Radio 1 Network " + JSON.stringify({timestamp_ms: Date.now(),
            event: reason, previous: previous, current: current}))
        previous = current
        observed(reason)
        connectivityObserved(current)
    }
    NetworkManager { id: manager }
    NetworkTechnology { id: wifi; path: Connman.wifiTechnologyPath }
    Connections {
        target: manager
        ignoreUnknownSignals: true
        onStateChanged: probe.snapshot("connman.state", true)
        onAvailabilityChanged: probe.snapshot("connman.available", true)
        onDefaultRouteChanged: probe.snapshot("connman.route", true)
        onConnectedWifiChanged: probe.snapshot("connman.wifi", true)
        onServicesChanged: probe.snapshot("connman.services", true)
        onTechnologiesChanged: probe.snapshot("connman.technologies", true)
    }
    Connections {
        target: manager.defaultRoute
        ignoreUnknownSignals: true
        onStateChanged: probe.snapshot("connman.route.state", true)
        onConnectedChanged: probe.snapshot("connman.route.connected", true)
        onErrorChanged: probe.snapshot("connman.route.error", true)
        onIpv4Changed: probe.snapshot("connman.route.ipv4", true)
        onEthernetChanged: probe.snapshot("connman.route.interface", true)
    }
    Connections {
        target: manager.connectedWifi
        ignoreUnknownSignals: true
        onStateChanged: probe.snapshot("connman.wifi.state", true)
        onIpv4Changed: probe.snapshot("connman.wifi.ipv4", true)
        onEthernetChanged: probe.snapshot("connman.wifi.interface", true)
        onErrorChanged: probe.snapshot("connman.wifi.error", true)
    }
    Connections {
        target: wifi
        ignoreUnknownSignals: true
        onPoweredChanged: probe.snapshot("connman.wifi.powered", true)
        onConnectedChanged: probe.snapshot("connman.wifi.connected", true)
        onPropertiesReady: probe.snapshot("connman.wifi.ready", true)
    }
    Timer { interval: 1000; repeat: true; running: true
        onTriggered: probe.snapshot("connman.snapshot", false) }
    Component.onCompleted: snapshot("connman.observer_created", true)
    Component.onDestruction: if (diagnosticLogging) console.warn("Felis Radio 1 Network " + JSON.stringify({
        timestamp_ms: Date.now(), event: "connman.observer_destroyed"}))
}
