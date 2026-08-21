package com.iris.companion

import android.content.Context
import android.net.wifi.WifiManager
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

object DiscoveryManager {

    private const val DISCOVERY_PORT = 15503
    private const val REQUEST_MSG = "IRIS_DISCOVER_REQ"
    private const val RESPONSE_PREFIX = "IRIS_DISCOVER_RESP|"

    fun discoverServer(context: Context, timeoutMs: Int = 2000): String? {
        var socket: DatagramSocket? = null
        var multicastLock: WifiManager.MulticastLock? = null
        try {
            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            multicastLock = wifi?.createMulticastLock("IrisDiscoveryLock")?.apply {
                setReferenceCounted(true)
                acquire()
            }

            socket = DatagramSocket().apply {
                broadcast = true
                soTimeout = timeoutMs
            }

            val sendData = REQUEST_MSG.toByteArray(Charsets.UTF_8)
            val broadcastAddr = InetAddress.getByName("255.255.255.255")
            val sendPacket = DatagramPacket(sendData, sendData.size, broadcastAddr, DISCOVERY_PORT)

            socket.send(sendPacket)

            val receiveData = ByteArray(1024)
            val receivePacket = DatagramPacket(receiveData, receiveData.size)

            socket.receive(receivePacket)

            val response = String(receivePacket.data, 0, receivePacket.length, Charsets.UTF_8).trim()
            if (response.startsWith(RESPONSE_PREFIX)) {
                return response.substring(RESPONSE_PREFIX.length)
            }
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            try {
                multicastLock?.release()
            } catch (_: Exception) {}
            socket?.close()
        }
        return null
    }
}
