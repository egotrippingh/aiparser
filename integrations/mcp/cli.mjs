#!/usr/bin/env node
import { serveStdio } from "@modelcontextprotocol/server/stdio"
import { createAirateServer } from "./server.mjs"
import packageInfo from "./package.json" with { type: "json" }

const key = process.env.AIRATE_API_KEY?.trim()
if (process.argv.includes("--version")) {
  console.log(packageInfo.version)
} else if (!key) {
  console.error("Set AIRATE_API_KEY before starting the AIRate MCP server.")
  process.exitCode = 1
} else {
  serveStdio(() => createAirateServer({ key, version: packageInfo.version }))
}
