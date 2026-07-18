package io.legado.headless

import io.legado.headless.protocol.RuntimeServer

fun main(args: Array<String>) {
    if (args.contains("--version")) {
        println("legado-runtime protocol=1 engine=2c340d48bb1b9537690ec31eb9c23a57307f30a3")
        return
    }
    val server = RuntimeServer()
    generateSequence(::readLine).forEach { line ->
        println(server.dispatchLine(line))
    }
}
