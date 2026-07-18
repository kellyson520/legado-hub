package io.legado.headless

fun main(args: Array<String>) {
    if (args.contains("--version")) {
        println("legado-runtime protocol=1 engine=2c340d48bb1b9537690ec31eb9c23a57307f30a3")
        return
    }
    generateSequence(::readLine).forEach { println(it) }
}
