package io.legado.headless

import io.legado.headless.protocol.RuntimeServer
import io.legado.headless.protocol.StdioCacheBridge
import io.legado.headless.protocol.StdioHttpBridge
import io.legado.headless.ports.HeadlessRuntimeBridges
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter

fun main(args: Array<String>) {
    if (args.contains("--version")) {
        println("legado-runtime protocol=1 engine=2c340d48bb1b9537690ec31eb9c23a57307f30a3")
        return
    }
    val input = BufferedReader(InputStreamReader(System.`in`))
    val output = PrintWriter(System.out, true)
    HeadlessRuntimeBridges.http = StdioHttpBridge(input, output)
    HeadlessRuntimeBridges.cache = StdioCacheBridge(input, output)
    val server = RuntimeServer()
    while (true) {
        val line = input.readLine() ?: break
        output.println(server.dispatchLine(line))
    }
}
