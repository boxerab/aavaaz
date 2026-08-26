# SSO with an OpenID Connect provider

Aavaaz's SaaS API accepts RS256 bearer tokens from any OpenID Connect provider.
It fetches the provider's JWKS, caches the keys in memory, and re-fetches when a
token arrives with a key id it has not seen (so key rotation needs no restart).

Keycloak is used as the worked example below. Cognito, Auth0 and Okta differ
only in the two URLs.

## Configuration

Three environment variables, read by `aavaaz/api/auth.py`:

| Variable | Value |
|----------|-------|
| `AAVAAZ_JWT_JWKS_URL` | the provider's JWKS endpoint |
| `AAVAAZ_JWT_ISSUER` | expected `iss` claim, must match exactly (trailing slashes count) |
| `AAVAAZ_JWT_AUDIENCE` | expected `aud` claim, usually the client ID. Leave unset to skip the audience check |

They apply to both SaaS implementations: the self-hosted API
(`python -m aavaaz.saas_server`) and the Lambda (`aavaaz/serverless/saas_lambda.py`).
`AAVAAZ_JWT_SECRET` stays the HS256 option for locally issued tokens, and the two
coexist: the token's `alg` header picks the path.

The Lambda defaults all three to its Cognito pool, derived from
`AAVAAZ_COGNITO_REGION`, `AAVAAZ_COGNITO_POOL_ID` and `AAVAAZ_COGNITO_CLIENT_ID`,
so a Cognito deployment sets nothing extra.

## Provider URL shapes

### Keycloak

```
AAVAAZ_JWT_ISSUER=https://keycloak.example.com/realms/<realm>
AAVAAZ_JWT_JWKS_URL=https://keycloak.example.com/realms/<realm>/protocol/openid-connect/certs
AAVAAZ_JWT_AUDIENCE=<client-id>
```

### AWS Cognito

```
AAVAAZ_JWT_ISSUER=https://cognito-idp.<region>.amazonaws.com/<pool-id>
AAVAAZ_JWT_JWKS_URL=https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/jwks.json
AAVAAZ_JWT_AUDIENCE=<app-client-id>
```

Cognito id tokens carry `token_use: id`. The Lambda rejects access tokens on that
claim, so send the id token.

### Auth0

```
AAVAAZ_JWT_ISSUER=https://<tenant>.auth0.com/
AAVAAZ_JWT_JWKS_URL=https://<tenant>.auth0.com/.well-known/jwks.json
AAVAAZ_JWT_AUDIENCE=<api-identifier>
```

The Auth0 issuer ends in a slash.

### Okta

```
AAVAAZ_JWT_ISSUER=https://<tenant>.okta.com/oauth2/<authorization-server-id>
AAVAAZ_JWT_JWKS_URL=https://<tenant>.okta.com/oauth2/<authorization-server-id>/v1/keys
AAVAAZ_JWT_AUDIENCE=<audience>
```

For the org authorization server the path is `/oauth2/v1/keys` with no server id.

## Keycloak setup

### 1. Create a client

In the Admin Console, **Clients → Create client**:

- **Client ID**: `aavaaz`
- **Client type**: OpenID Connect
- **Client authentication**: Off for a browser app, On for a service account
- **Standard flow**: on (browser login)
- **Direct access grants**: on (CLI and scripts)
- **Valid redirect URIs**: your dashboard origin plus `/*`

### 2. Add a role mapper

Aavaaz reads roles from the `role` claim.

1. **Clients → aavaaz → Client scopes → aavaaz-dedicated**
2. **Add mapper → By configuration → User Realm Role**
3. Name `role-mapper`, Token Claim Name `role`, Claim JSON Type `String`
4. Add to ID token and access token, Multivalued off

Create the realm roles `admin`, `user` and `readonly` under **Realm roles** and
assign them under **Users → [user] → Role mappings**.

### 3. Start the API

```bash
export KEYCLOAK_REALM_URL="https://keycloak.example.com/realms/aavaaz"
export AAVAAZ_JWT_JWKS_URL="${KEYCLOAK_REALM_URL}/protocol/openid-connect/certs"
export AAVAAZ_JWT_ISSUER="${KEYCLOAK_REALM_URL}"
export AAVAAZ_JWT_AUDIENCE="aavaaz"

python -m aavaaz.saas_server
```

### Docker Compose

```yaml
services:
  aavaaz-saas:
    image: aavaaz:latest
    command: python -m aavaaz.saas_server
    environment:
      - AAVAAZ_JWT_JWKS_URL=https://keycloak.example.com/realms/aavaaz/protocol/openid-connect/certs
      - AAVAAZ_JWT_ISSUER=https://keycloak.example.com/realms/aavaaz
      - AAVAAZ_JWT_AUDIENCE=aavaaz
    ports:
      - "8001:8001"
```

## Getting a token

### Password grant (CLI and scripts)

```bash
TOKEN=$(curl -s -X POST \
  "https://keycloak.example.com/realms/aavaaz/protocol/openid-connect/token" \
  -d "client_id=aavaaz" \
  -d "grant_type=password" \
  -d "username=alice" \
  -d "password=secret" \
  | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/v1/saas/usage
```

### Client credentials (machine to machine)

Enable **Client authentication** and **Service accounts roles** on the client,
then:

```bash
TOKEN=$(curl -s -X POST \
  "https://keycloak.example.com/realms/aavaaz/protocol/openid-connect/token" \
  -d "client_id=aavaaz" \
  -d "client_secret=$CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  | jq -r '.access_token')
```

### Browser login

The dashboard obtains the token through its own provider SDK (Amplify for
Cognito, keycloak-js for Keycloak) and sends it as `Authorization: Bearer`.

## Troubleshooting

The Lambda puts the underlying reason in the 401 body. The self-hosted server
answers a plain `Invalid token`, so match on the cause instead.

| Problem | Fix |
|---------|-----|
| `401 Invalid token: Invalid audience` | `AAVAAZ_JWT_AUDIENCE` does not match the token's `aud`. Decode the token: `echo "$TOKEN" \| cut -d. -f2 \| base64 -d \| jq .` |
| `401 Invalid token: Invalid issuer` | `AAVAAZ_JWT_ISSUER` must equal `iss` character for character, trailing slash included |
| `401 Invalid token: No JWKS key for kid` | The token was signed by a key the provider does not publish, or `AAVAAZ_JWT_JWKS_URL` points at another realm |
| `401 Invalid token: RS256 token received but AAVAAZ_JWT_JWKS_URL is not set` | The three variables are missing from the process environment |
| `401 Wrong token type` | Cognito access token sent instead of the id token |
| `URLError` on the first request | The API cannot reach the JWKS URL. Inside Docker use the container network hostname |

## Security notes

- Provider access tokens are short-lived (5 minutes on Keycloak by default).
  Refresh them client-side rather than lengthening the lifespan.
- Use HTTPS for both the provider and Aavaaz.
- Use PKCE for browser clients.
