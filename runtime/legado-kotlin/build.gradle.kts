plugins {
    kotlin("jvm") version "2.4.0"
    application
}

group = "io.legado.headless"
version = "0.1.0"

repositories {
    mavenCentral()
}

dependencies {
    implementation(kotlin("stdlib"))
    implementation("com.google.code.gson:gson:2.14.0")
    implementation("org.jsoup:jsoup:1.16.2")
    implementation("cn.wanghaomiao:JsoupXpath:2.5.5")
    implementation("com.jayway.jsonpath:json-path:3.0.0")
    implementation("org.mozilla:rhino:1.8.1")
    implementation("org.apache.commons:commons-text:1.15.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.11.0")

    testImplementation(kotlin("test"))
}

application {
    mainClass.set("io.legado.headless.MainKt")
}

kotlin {
    jvmToolchain(17)
}

sourceSets {
    main {
        kotlin.srcDir("vendor")
    }
}

tasks.test {
    useJUnitPlatform()
}

tasks.jar {
    manifest {
        attributes["Main-Class"] = application.mainClass.get()
    }
}
