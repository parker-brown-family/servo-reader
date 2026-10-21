# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability. Report it
privately through GitHub's
[Report a vulnerability](https://github.com/parker-brown-family/servo-reader/security/advisories/new)
form, on the repository's Security tab under Advisories.

Include what the problem lets someone do, the steps or a page that reproduce it,
and the commit or `sr --version` you tested.

## Scope

servo-reader fetches the pages you ask it to read. With `--images` it also
fetches the images those pages reference, and because a page chooses those URLs,
image requests go only to `http` and `https` hosts that resolve to public
addresses. Loopback, private, link-local, multicast, reserved and unspecified
addresses are refused, and each redirect is checked again before it is followed.

When a page is rendered with Servo, the engine runs that page's JavaScript. Treat
the pages you read as untrusted, and treat what servo-reader prints the same way
when you pass it on to another program or to an LLM.

Report problems in the Servo engine to the
[Servo project](https://github.com/servo/servo/security). The distiller and the
WebDriver client belong to
[servo-agent](https://github.com/parker-brown-family/servo-agent/security).

## Supported versions

There are no releases yet. Fixes land on `main`.
