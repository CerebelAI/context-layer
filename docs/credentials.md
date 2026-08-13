# Credentials and data

- All credentials live in `.env`. Never hardcode a key.
- IMPORTANT: never write a fake, stubbed, or sample implementation of a connector to work around
  missing credentials. If a credential is missing, STOP and ask for it.
- Never invent sample or demo data to make a pipeline appear to work.
- Test doubles inside `tests/` are the exception and are expected. Tests must not make live API
  calls.
