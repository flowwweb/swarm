# Supporter logos

Edit `../../supporters.json` to change supporter order, names, and HTTPS links.
Use `null` for an unconfirmed destination or unavailable logo. A logo must name
an admitted file in `SUPPORTER_LOGOS` in `scripts/swarm_mcp.py`; its original
bytes and SHA-256 are checked before embedding. After changing the JSON, update
its SHA-256 in `PROJECTS_ASSETS` and follow the repository's mirror and review
workflow. This is a source configuration, not an in-app editor.

The legacy Flowwweb case-study files are retained for provenance. Nemo's selected
sharp-base trident master and Helm's original production master remain unverified.
RightWork uses the unchanged `assets/brand/rightwork-logo-white.svg` from
`flowwweb/RightWork@bf50ffe94fba28708ab74ea8e5a13360ae0fb668`
(SHA-256 `866fefb211dafac9cea9ab4a12155cc0639145f1fef81c385af509190c6ccc2e`).
The prior `rightwork-logo.svg` is retained but is not the selected source.
Unbake matches `public/unbake-logo.svg` from
`flowwweb/unbake@b45f7eeeb40e64ef35c949aaa6a6923e1c9e40e3`
(SHA-256 `41cd55104f31dad02a3927ffbcfe3a3021de62db1b8918cffbd9c20011d471cc`).
WHXTEVER's exact warm wordmark comes from
`https://whxtever.com/brand/warm/wordmark.svg` (SHA-256
`c5de578a2a2c7ab4e49e6693eed0a7fb73bd1ea4565b9239a3bdb6e600d1ef21`);
the Nunito font license is retained in `NUNITO-OFL.txt`.
Bluprint: `bluprint-wordmark-alpha-990.png` is a transparent 990 x 250
raster rendered directly from the unchanged canonical SVG at
`C:/Projects/bluprint/apps/editor/public/brand/bluprint-wordmark-alpha.svg`
(public source: `https://bluprint.web.app/brand/bluprint-wordmark-alpha.svg`;
SHA-256 `71a841154b492f18bc247870583854d0136f71f11e458e245294e5e454525f66`).
The PNG SHA-256 is `700c1fde2233f42ca4a1a87f94de375d5f92827ae26af7f7941ec7407961869f`.
The 990 x 250 Chrome raster comparison had zero differing RGBA pixels; the
original SVG was not changed. Theme color is applied in presentation CSS.
