# SQLAlchemy Async PostgreSQL Locking Demo

These tests validate the transactional integrity and concurrency control of the SQLAlchemyEventClaimManager.

Lock Contention Test: Simulates two consumers with independent database connection pools attempting to claim the same event ID. It asserts that the database's row-level or advisory locking mechanism correctly prevents the second consumer from proceeding while the first consumer's transaction is in-flight, raising a LockContentionError.

Transactional Rollback Test: Verifies the atomicity of the claim-and-process operation. It shows that when a consumer's transaction is rolled back after claiming an event, all database changes (including the lock) are reverted, leaving the event available for another consumer to claim and process successfully.


## Prerequisites

Before you begin, ensure you have the following installed on your system:

-   **Docker & Docker Compose**: To run the PostgreSQL database. [Install Docker](https://docs.docker.com/get-docker/)
-   **uv**: The Python package installer and virtual environment manager. [Install uv](https://github.com/astral-sh/uv#installation)

## Getting Started

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```

2.  **Install Python dependencies:**
    The project uses `uv` to manage dependencies defined in `pyproject.toml`. The `make` commands will handle this automatically, but you can sync the environment manually if you wish:
    ```bash
    uv sync
    ```

## Usage

This project uses a `Makefile` to simplify common tasks.

### Running the Demonstration

The main command will start the database and run the locking test script.

```bash
make test
```

This command performs two actions:
1.  `docker compose up -d`: Starts a PostgreSQL 16 database in a detached Docker container.
2.  `uv run pytest ...`: Executes the test script, which simulates the two consumers and prints detailed logs to the console.

### Understanding the Log Output

When you run the tests, the logs demonstrate a **non-blocking** lock strategy using PostgreSQL's transaction-level advisory locks. This means consumers fail fast rather than waiting for a lock to be released. Here is the sequence of events to watch for in each test.

#### Test 1: `test_consumer_b_cannot_lock_when_a_holds_lock`

This test demonstrates that a second consumer cannot process an event that is already locked.

1.  **Consumer A Acquires Lock**: The test begins, and you'll see Consumer A successfully acquire its lock inside a transaction.
    ```log
    INFO     ... [Consumer A] Starting, will acquire lock
    DEBUG    ... Advisory lock acquired for event: ...
    INFO     ... Claim successfully established for Event ...
    ```

2.  **Consumer B Attempts Lock & Fails Immediately**: Before Consumer A's transaction is complete, Consumer B attempts to claim the same event. Because the implementation uses a *non-blocking* lock, it doesn't wait. It fails instantly.
    ```log
    INFO     ... [Consumer B] Starting, will attempt to acquire lock
    DEBUG    ... Attempting to acquire advisory lock for event ...
    INFO     ... [Consumer B] Caught expected error: Event '...' is locked by another consumer.
    ```
    This `Caught expected error` message is the key outcome, proving that the system correctly prevents concurrent processing.

3.  **Consumer A Finishes**: Much later, Consumer A completes its `asyncio.sleep` and commits its transaction.
    ```log
    INFO     ... [Consumer A] Transaction committed
    ```

#### Test 2: `test_consumer_b_cannot_lock_when_a_has_processed`

This test demonstrates that a second consumer cannot processed a completed event.

1.  **Consumer A Acquires Lock**: The test begins, and you'll see Consumer A successfully acquire its lock inside a transaction.
    ```log
    INFO     ... [Consumer A] Starting, will acquire lock
    DEBUG    ... Advisory lock acquired for event: ...
    INFO     ... Claim successfully established for Event ...
    ```

2.  **Consumer A Finishes**: Consumer A completes and commits its transaction.
    ```log
    INFO     ... [Consumer A] Transaction committed
    ```

3.  **Consumer B Attempts Lock & Fails Immediately**: After Consumer A's transaction is complete, Consumer B attempts to claim the same event.
    ```log
    INFO     ... [Consumer B] Starting, will attempt to acquire lock
    DEBUG    ... Attempting to acquire advisory lock for event ...
    INFO     ... [Consumer B] Caught expected error: Event '...' already completed.
    ```
    This `Caught expected error` message is the key outcome, proving that the system correctly prevents re-processing a completed event.

#### Test 3: `test_consumer_b_can_process_after_a_fails_and_rolls_back`

This test demonstrates the system's fault tolerance.

1.  **Consumer A Acquires Lock then Fails**: Consumer A successfully claims the event but then encounters a simulated error.
    ```log
    INFO     ... [Consumer A] ... acquire lock and then fail
    INFO     ... Claim successfully established for Event ...
    INFO     ... [Consumer A] Lock acquired, now raising error
    ```

2.  **Transaction is Rolled Back**: The error causes its `UnitOfWork` to roll back the transaction. This releases the advisory lock and discards the inserted event record.
    ```log
    WARNING  ... Exception in UnitOfWork context: ValueError: Simulating a processing failure
    INFO     ... [Consumer A] Caught exception, UoW rolled back
    ```

3.  **Consumer B Succeeds**: Now that the lock is released, Consumer B can start its work. It successfully acquires the lock and processes the event, proving the system has recovered from Consumer A's failure.
    ```log
    INFO     ... [Consumer B] Starting, will attempt to acquire lock
    DEBUG    ... Advisory lock acquired for event: ...
    INFO     ... Claim successfully established for Event ...
    INFO     ... [Consumer B] Transaction committed successfully
    ```
    The successful commit by Consumer B confirms that the rollback by Consumer A was clean and left the event in a processable state.

### Code Quality and Formatting

The following commands are available for development:

-   **Format code:** Automatically formats all source files using `ruff`.
    ```bash
    make format
    ```

-   **Lint code:** Checks for dependency lockfile consistency, type errors with `mypy`, and formatting/style issues with `ruff`.
    ```bash
    make lint
    ```

### Cleaning Up

To stop and remove the PostgreSQL database container and its associated network:

```bash
docker compose down
```

To remove the database volume as well (deleting all data):

```bash
docker compose down -v
```