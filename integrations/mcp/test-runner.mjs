import { serveStdio } from "@modelcontextprotocol/server/stdio"
import { createAirateServer } from "./server.mjs"

const [baseUrl] = process.argv.slice(2)
serveStdio(() => createAirateServer({ key: process.env.AIRATE_API_KEY, baseUrl, version: "test" }))
