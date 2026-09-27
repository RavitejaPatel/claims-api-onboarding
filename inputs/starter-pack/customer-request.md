# Customer request

We need to deploy `claims-api` for a pilot. It should be reachable at
`claims-api.<environment>.apps.example.invalid`, deploy from our container image, and
connect to our managed PostgreSQL database. Please make dev automatic and give us a
repeatable path to stage. We can provide a database password, but we do not want it in
Git. We need to know who owns incidents and how to undo a bad release.
