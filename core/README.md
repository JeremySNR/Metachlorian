# metachlorian (core)

The headless core of [Metachlorian](https://github.com/JeremySNR/Metachlorian): ingest, shot-level analysis, hybrid search, REST API and MCP server.

Photo indexing and Lightroom Classic editing are available as a preview feature. Install `metachlorian[photos]`, fetch `models fetch --pack photos`, and enable Photos in the web app. See [photo setup and current limits](https://github.com/JeremySNR/Metachlorian/blob/main/docs/photos.md).

```bash
pip install "metachlorian[analysis]"
metachlorian models fetch
metachlorian serve --add ~/Footage
```
