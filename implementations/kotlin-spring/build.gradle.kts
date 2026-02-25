plugins { kotlin("jvm") version "1.9.24"; kotlin("plugin.spring") version "1.9.24"; id("org.springframework.boot") version "3.3.2"; id("io.spring.dependency-management") version "1.1.6" }
repositories { mavenCentral() }
dependencies { implementation("org.springframework.boot:spring-boot-starter-web") }
