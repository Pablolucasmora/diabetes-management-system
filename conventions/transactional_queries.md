# Database Transaction Convention

This project uses psycopg 3 and follows one transaction ownership rule:

> The layer that coordinates multiple database operations owns the transaction.

## Query helpers

- `_execute_query()` and `_execute_query_many()` keep `commit=True` as their default for backward compatibility.
- Read-only calls must use `commit=False`.
- Write helpers must expose `commit: bool = True` and pass it to the query helper.
- A write helper must never call `commit()` when `commit=False`.
- A write helper must not roll back a transaction owned by its caller.
- SQL exceptions must be propagated when a helper is running inside a caller-owned transaction. Query helpers use `rollback_on_error=False` for this mode.

## Composed operations

Endpoints or services coordinating multiple writes must use one transaction:

```python
try:
    with connection.transaction():
        first_write(connection, ..., commit=False)
        second_write(connection, ..., commit=False)
except Exception:
    return error_response()
```

All writes either commit together or roll back together. The coordinator must check expected false/None results and raise an exception when they represent a failed operation.

## Error contract

- `False`/`None` may represent an expected business result such as “not found”.
- Database and infrastructure failures must not be silently converted into a successful result.
- Functions participating in a caller-owned transaction must let database exceptions propagate.
- Do not call `connection.rollback()` inside a helper when `commit=False`.

## Direct cursors

Direct cursors are valid when a function needs multiple statements, intermediate rows, or `rowcount`. They must still accept `commit` and follow the same ownership rules. Using a cursor directly does not grant the function ownership of the transaction.

## New code checklist

Before adding a database write:

1. Add `commit: bool = True` to the write helper.
2. Avoid unconditional `commit()` and `rollback()` calls.
3. Pass `commit=False` from composed operations.
4. Raise on database failure inside caller-owned transactions.
5. Add a rollback test for every multi-write operation.

`db_init.py` is schema bootstrap code and keeps its own startup transaction; it is not part of application CRUD transactions.
