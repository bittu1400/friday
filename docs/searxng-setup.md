# SearXNG setup (G7, ADR-045)

Friday's only egress. A loopback-only SearXNG in Docker, managed as a
`systemd --user` unit. Nothing binds beyond `127.0.0.1` (invariant #8 / FR-60).

## Pinned image

```
docker.io/searxng/searxng@sha256:11a9b34cdc0b1ec2b991470a2762ecb5a1a531898289fb51dcd015260450729e
```

Pin by digest (never `:latest` at runtime). To re-pin after an intentional
bump: `docker pull searxng/searxng:latest` then
`docker inspect --format='{{index .RepoDigests 0}}' searxng/searxng:latest`,
and replace the digest in `deploy/searxng/friday-searxng.service` and here.

## One-time install

```bash
systemctl --user daemon-reload
systemctl --user link "$PWD/deploy/searxng/friday-searxng.service"
systemctl --user start friday-searxng
```

`dockerd` is a **system** service (`docker.service`, enabled at boot). A
`--user` unit cannot depend on it by name — user scope has no `docker.service` —
so the unit expresses no cross-scope dependency and relies on dockerd being up.

## Verify (loopback assertion)

```bash
curl -s 'http://127.0.0.1:8888/search?q=test&format=json' | head -c 200
ss -ltnp | grep 8888
```

Expected: a JSON object beginning `{"query": "test"`; `ss` shows a
`127.0.0.1:8888` LISTEN and **no** `0.0.0.0:8888` bind. The host side of the
docker port map (`-p 127.0.0.1:8888:8080`) is loopback-only; the container
binds `0.0.0.0:8080` internally, which is not reachable off-host.

## Manage

```bash
just searxng start
just searxng stop
just searxng status
```

## Note

This is the first of the three G9 service units.
