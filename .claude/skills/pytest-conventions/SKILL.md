---
name: pytest-conventions
description: Apply pytest conventions when writing or reviewing tests. Use when asked to write tests, add a test, or review test quality.
user-invocable: true
---

## Pytest Conventions

Apply these rules to every test you write or review.

---

### Test naming

```
test_<method_or_behaviour>__<condition>__<expected_outcome>
```

Examples:
- `test_get_by_slug__slug_not_found__returns_none`
- `test_create_user__email_already_taken__raises_conflict`
- `test_verify_token__token_expired__returns_false`

---

### Structure: AAA

Every test uses three comment-marked sections:

```python
async def test_something__condition__outcome() -> None:
    # Arrange

    # Act

    # Assert
```

No exceptions. Even if Arrange is a single line.

---

### Fixtures over helper functions

Never write a plain function inside a test file for shared setup. Always use a pytest fixture.

**Wrong:**
```python
def create_user(client):
    return client.post("/users", json={...})

async def test_something(client):
    user = create_user(client)
```

**Right — simple fixture:**
```python
# conftest.py
@pytest_asyncio.fixture
async def existing_user(client):
    response = await client.post("/users", json={...})
    return response.json()
```

**Right — callable fixture** (when you need multiple instances or varying inputs):
```python
# conftest.py
@pytest.fixture
def create_user(client):
    async def _create(email="test@example.com"):
        response = await client.post("/users", json={"email": email})
        return response.json()
    return _create

# test file
async def test_something(create_user):
    user = await create_user()
```

Put fixtures in `conftest.py` when shared across multiple test files. If a callable fixture is only used in one file, it can live in that file. Return a coroutine function when the inner logic is async.

---

### No mocking

Do not mock the database, repositories, or internal services. Test against real implementations.

Mocks verify that you called something — not that it works. Real implementations catch integration bugs that mocks hide.

Acceptable mocks: external HTTP APIs, third-party SDKs, email/SMS senders — anything that makes real network calls or has side effects outside your control.

---

### Factories for test data

Use factories (e.g. `polyfactory`, `factory_boy`) to build model instances. Do not construct domain objects inline in tests — it couples tests to constructor signatures.

```python
# Good
user = UserFactory.build(is_active=False)

# Bad
user = User(id=1, name="Test", email="t@t.com", is_active=False, created_at=...)
```

Override only the fields relevant to the test case. Let the factory provide the rest.

---

### Imports

Use absolute imports in all test files. Never use relative imports.
