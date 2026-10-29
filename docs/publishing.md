# Transfer and publish @avandar/markdown-to-pdf

The package is configured for the public npm registry as
`@avandar/markdown-to-pdf`, version `0.15.0`. Its executable remains
`markdown-to-pdf`. These commands are manual steps; no transfer, push, or
publication has been performed by preparing this guide.

## 1. Transfer GitHub ownership

Run from your local main checkout. The authenticated GitHub account needs
repository administrator access and permission to create repositories in
AvandarLabs. The destination must not already contain a conflicting repository.
GitHub and npm organization permissions are independent.

```sh
gh auth status
gh api --method POST repos/jpsyx/markdown-to-pdf/transfer \
  -f new_owner=AvandarLabs
```

The API returns acceptance of an asynchronous transfer. Wait for it to complete,
then verify the owner before updating the remote:

```sh
gh api repos/AvandarLabs/markdown-to-pdf --jq .full_name
git remote set-url origin https://github.com/AvandarLabs/markdown-to-pdf.git
git push origin main
```

The verification must print `AvandarLabs/markdown-to-pdf`. Do not force-push if
Git reports that the remote has newer commits. Transferring preserves the
repository's history and normally redirects the old URL. Review organization
access and Actions policies after transfer.

Source: [GitHub repository transfer API](https://docs.github.com/en/rest/repos/repos#transfer-a-repository).

## 2. Publish the first version to npm

Use an npm account with permission to publish under the `avandar` scope. Complete
npm's account authentication and any required two-factor verification. Owning
the GitHub organization does not grant npm scope access.

From the main checkout, with Node.js 20+ and Python 3.10+ installed:

```sh
npm login --registry=https://registry.npmjs.org/
npm whoami --registry=https://registry.npmjs.org/
npm run test:npm
npm pack --dry-run
npm publish --access public --registry=https://registry.npmjs.org/
npm view @avandar/markdown-to-pdf version --registry=https://registry.npmjs.org/
```

Review the dry-run file list before publishing. If your default `python3` is
older than 3.10, set `MARKDOWN_TO_PDF_PYTHON` to a supported Python executable
before testing. The test installs dependencies from the network in temporary
local and global prefixes. Publication is public and requires a version not
already present on npm. `publishConfig` also sets public visibility and the
registry, so a later plain `npm publish` uses the same destination.

No GitHub secret, GitHub Packages configuration, or Python package publication
is required for this manual npm publication path. The GitHub transfer is useful
for ownership and matching repository metadata, but is not what grants npm
publishing rights.

Source: [npm scoped public packages](https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/).

## 3. Install as a consumer

```sh
npm install --save-dev @avandar/markdown-to-pdf
npm exec -- markdown-to-pdf docs/guide.md --out guide.pdf

# Or install a globally available command:
npm install --global @avandar/markdown-to-pdf
markdown-to-pdf docs/guide.md --out guide.pdf
```

Consumers still need Python 3.10+ with venv and pip. The first invocation
installs the Python dependencies into a private user cache. Mermaid diagrams
also require the optional renderer's browser. See the README for CI details.

## 4. Later releases and optional automation

Change `__version__` in `main.py` using semver, then run
`node scripts/sync-version.cjs` before committing. Commit both version changes;
`npm pack` and `npm publish` also run this synchronization through `prepack`.
Test, push the release commit, and publish the new version. An existing npm
version cannot be overwritten.

For automated GitHub Actions publication, use npm trusted publishing instead
of a long-lived npm token. This repository does not yet include a publishing
workflow. After creating one, configure the package on npmjs.com:
Packages > @avandar/markdown-to-pdf > Settings > Trusted publishing > GitHub Actions.
Use organization `AvandarLabs`, repository `markdown-to-pdf`, and the exact
workflow filename you create (for example `publish.yml`). Grant publishing
permission in that configuration. The workflow needs `id-token: write`, a
supported npm CLI, and an `npm publish` step. This is optional; steps 1 and 2
are sufficient for manual publishing.

Source: [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/).
