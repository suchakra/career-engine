"""In-memory Firestore test doubles (moved out of the production module, 1.7-D).

These fakes used to live in ``database/firestore_session.py``; they are
test-only and were relocated here so the production runtime module contains no
test scaffolding.  ``FirestoreSessionService`` accepts any object with this
client surface via its ``client=`` injection point.

The real ``google.cloud.firestore.AsyncClient`` supports chained calls like::

    client.collection("a").document("b").collection("c").document("d").set(data)

To replicate that with a flat in-memory dict, every node in the chain just
accumulates path segments and the terminal methods (set / get / delete /
list_documents) operate on the complete assembled path.  This is intentionally
minimal — only the surface used by ``FirestoreSessionService`` — NOT a general
Firestore emulator.
"""

from __future__ import annotations

from typing import Any


class _FakeDocumentSnapshot:
    """Minimal DocumentSnapshot used by the in-memory fake."""

    def __init__(self, data: dict[str, Any] | None, path: str) -> None:
        """Initialise a fake snapshot.

        Args:
            data: The document data, or None if the document does not exist.
            path: The Firestore document path (informational).
        """
        self._data = data
        self.path = path

    @property
    def exists(self) -> bool:
        """True if the document exists in the fake store."""
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        """Return the document data, or None if the document does not exist."""
        return self._data


class _FakeDocumentReference:
    """Minimal async DocumentReference backed by a shared flat dict store.

    Supports .collection() for sub-collection chaining.
    """

    def __init__(self, store: dict[str, dict[str, Any]], path: str) -> None:
        """Initialise a document reference.

        Args:
            store: Shared mutable dict mapping absolute path -> document data.
            path: The absolute Firestore path for this document.
        """
        self._store = store
        self.path = path

    def collection(self, collection_id: str) -> _FakeCollectionReference:
        """Return a sub-collection reference under this document.

        Args:
            collection_id: The sub-collection name.

        Returns:
            A _FakeCollectionReference whose prefix is ``{self.path}/{collection_id}``.
        """
        return _FakeCollectionReference(
            store=self._store, prefix=f"{self.path}/{collection_id}"
        )

    async def set(self, document_data: dict[str, Any], merge: bool = False) -> None:
        """Write document_data to this document path.

        Args:
            document_data: The data to write.
            merge: If True, merge into the existing document instead of overwriting.
        """
        if merge and self.path in self._store:
            self._store[self.path].update(document_data)
        else:
            self._store[self.path] = dict(document_data)

    async def get(self) -> _FakeDocumentSnapshot:
        """Return a snapshot for this document.

        Returns:
            A snapshot whose .exists reflects whether data was stored at this path.
        """
        raw = self._store.get(self.path)
        data = dict(raw) if raw is not None else None
        return _FakeDocumentSnapshot(data=data, path=self.path)

    async def delete(self) -> None:
        """Delete this document if it exists (no-op if absent)."""
        self._store.pop(self.path, None)


class _FakeCollectionReference:
    """Minimal async CollectionReference backed by a shared flat dict store."""

    def __init__(self, store: dict[str, dict[str, Any]], prefix: str) -> None:
        """Initialise a collection reference.

        Args:
            store: Shared mutable dict mapping absolute path -> document data.
            prefix: The absolute path prefix for this collection (no trailing slash).
        """
        self._store = store
        self._prefix = prefix.rstrip("/")

    def document(self, doc_id: str) -> _FakeDocumentReference:
        """Return a reference to a document in this collection.

        Args:
            doc_id: The document ID.

        Returns:
            A _FakeDocumentReference at ``{prefix}/{doc_id}``.
        """
        return _FakeDocumentReference(store=self._store, path=f"{self._prefix}/{doc_id}")

    async def list_documents(self) -> list[_FakeDocumentReference]:
        """Return references to all existing direct-child documents.

        Only documents that are direct children of this collection (no further
        path segments after the document ID) are returned.

        Returns:
            A list of _FakeDocumentReference objects, one per existing document.
        """
        col_prefix = self._prefix + "/"
        seen: dict[str, bool] = {}
        refs: list[_FakeDocumentReference] = []
        for path in list(self._store.keys()):
            if path.startswith(col_prefix):
                remainder = path[len(col_prefix):]
                doc_id = remainder.split("/")[0]
                doc_path = col_prefix + doc_id
                if doc_id and doc_path not in seen:
                    seen[doc_path] = True
                    refs.append(_FakeDocumentReference(store=self._store, path=doc_path))
        return refs


class FakeFirestoreClient:
    """In-memory Firestore client for unit tests.

    Mimics the async Firestore client interface used by FirestoreSessionService.
    The backing store is a flat dict keyed by the full Firestore document path.

    Example::

        client = FakeFirestoreClient()
        service = FirestoreSessionService(client=client)
    """

    def __init__(self) -> None:
        """Initialise the in-memory store."""
        self._store: dict[str, dict[str, Any]] = {}

    def collection(self, path: str) -> _FakeCollectionReference:
        """Return a top-level collection reference.

        Args:
            path: The collection path (top-level name or slash-separated path).

        Returns:
            A _FakeCollectionReference for the given path.
        """
        return _FakeCollectionReference(store=self._store, prefix=path.strip("/"))

    @property
    def store(self) -> dict[str, dict[str, Any]]:
        """Expose the raw backing store for test assertions (read-only access)."""
        return self._store
