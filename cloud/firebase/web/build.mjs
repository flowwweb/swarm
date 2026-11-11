import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url)), dist = path.join(here, "dist"), repo = path.resolve(here, "../../..");
const packageJson = JSON.parse(await readFile(path.join(here, "node_modules/firebase/package.json"), "utf8"));
if (packageJson.version !== "12.15.0") throw new Error("UNEXPECTED_FIREBASE_VERSION");
const auth = await readFile(path.join(here, "node_modules/firebase/firebase-auth.js"), "utf8");
if (!auth.includes("https://www.gstatic.com/firebasejs/12.15.0/firebase-app.js")) throw new Error("UNEXPECTED_FIREBASE_MODULE");
await mkdir(path.join(dist, "vendor"), { recursive: true });
for (const name of ["firebase-app.js", "firebase-auth.js"]) await copyFile(path.join(here, "node_modules/firebase", name), path.join(dist, "vendor", name));
for (const name of ["index.html", "auth.mjs"]) await copyFile(path.join(here, name), path.join(dist, name));
await copyFile(path.join(repo, "skills/swarm/assets/swarm-wordmark.png"), path.join(dist, "swarm-wordmark.png"));
await copyFile(path.join(repo, "skills/swarm/assets/ui/swarm-hq-host.css"), path.join(dist, "swarm-hq-host.css"));
await writeFile(path.join(dist, "auth.css"), ".auth-page{max-width:420px;margin:12vh auto;padding:24px} .auth-page img{max-width:100%;height:auto}.auth-page button{min-height:44px;padding:0 18px}\n");
