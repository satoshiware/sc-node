git status
git add -A
git commit -m "Updating fixes to reward endpoint to improve time turnaround. 0.2.0"
git tag v0.2.0  
git push origin main
git push origin v0.2.0

$SHA = (git rev-parse --short HEAD).Trim()

# Build once, tag many (v0.2.0 + stable + sha; optionally latest)
$SHA = (git rev-parse --short HEAD).Trim()

docker build `
  -t ghcr.io/satoshiware/sc-node/master-api:latest:sha-$SHA `
  -t ghcr.io/satoshiware/sc-node/master-api:v0.2.0`.

docker push ghcr.io/satoshiware/sc-node/master-api:latest:sha-$SHA
docker push ghcr.io/satoshiware/sc-node/master-api:v0.2.0
