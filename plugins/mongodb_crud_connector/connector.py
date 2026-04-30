from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


def _load_pymongo() -> tuple[Any, Any]:
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pymongo is required; install plugins/mongodb_crud_connector/requirements.txt "
            "before running the real MongoDB connector."
        ) from exc
    return MongoClient, PyMongoError


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value.__class__.__name__ == "ObjectId":
        return str(value)
    return value


def _require_text(mapping: dict[str, Any], key: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing required argument: {key}")
    return value


def _require_object(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, dict) or not value:
        raise ValueError(f"argument {key} must be a non-empty object")
    return value


def _main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        capability = _require_text(request, "capability")
        arguments = request.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")

        operation_by_capability = {
            "mongodb_create": "create",
            "mongodb_read": "read",
            "mongodb_update": "update",
            "mongodb_delete": "delete",
            "mongodb_ping": "ping",
        }
        operation = operation_by_capability.get(capability)
        if operation is None:
            raise ValueError(f"unsupported capability: {capability}")

        MongoClient, PyMongoError = _load_pymongo()
        mongo_uri = _require_text(arguments, "mongo_uri")
        database_name = _require_text(arguments, "database")
        collection_name = _require_text(arguments, "collection")
        timeout_ms = int(arguments.get("server_selection_timeout_ms") or 3000)
        limit = max(1, min(int(arguments.get("limit") or 20), 100))
        many = bool(arguments.get("many", False))

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=timeout_ms)
        try:
            client.admin.command("ping")
            collection = client[database_name][collection_name]
            before_count = collection.estimated_document_count()

            if operation == "ping":
                output = {
                    "ping": "ok",
                    "database": database_name,
                    "collection": collection_name,
                    "document_count": collection.count_documents({}),
                }
            elif operation == "create":
                document = _require_object(arguments, "document")
                inserted = collection.insert_one(document)
                created = collection.find_one({"_id": inserted.inserted_id})
                if created is None:
                    raise RuntimeError("insert returned inserted_id but read-after-write found no document")
                output = {
                    "inserted_id": str(inserted.inserted_id),
                    "document": _json_safe(created),
                    "post_query_count": collection.count_documents({"_id": inserted.inserted_id}),
                }
            elif operation == "read":
                filter_doc = arguments.get("filter") or {}
                if not isinstance(filter_doc, dict):
                    raise ValueError("argument filter must be an object")
                documents = list(collection.find(filter_doc).limit(limit))
                output = {
                    "documents": _json_safe(documents),
                    "count": len(documents),
                    "matched_total": collection.count_documents(filter_doc),
                    "limit": limit,
                }
            elif operation == "update":
                filter_doc = _require_object(arguments, "filter")
                update_doc = _require_object(arguments, "update")
                operator_update = (
                    update_doc
                    if any(str(key).startswith("$") for key in update_doc)
                    else {"$set": update_doc}
                )
                response = (
                    collection.update_many(filter_doc, operator_update)
                    if many
                    else collection.update_one(filter_doc, operator_update)
                )
                after_documents = list(collection.find(filter_doc).limit(limit))
                output = {
                    "matched_count": response.matched_count,
                    "modified_count": response.modified_count,
                    "post_update_documents": _json_safe(after_documents),
                    "post_query_count": collection.count_documents(filter_doc),
                }
            else:
                filter_doc = _require_object(arguments, "filter")
                matched_before_delete = collection.count_documents(filter_doc)
                response = collection.delete_many(filter_doc) if many else collection.delete_one(filter_doc)
                output = {
                    "matched_before_delete": matched_before_delete,
                    "deleted_count": response.deleted_count,
                    "post_query_count": collection.count_documents(filter_doc),
                }

            after_count = collection.estimated_document_count()
            response_payload = {
                "status": "success",
                "output_summary": output,
                "before_evidence": {
                    "database": database_name,
                    "collection": collection_name,
                    "estimated_count": before_count,
                },
                "after_evidence": {
                    "database": database_name,
                    "collection": collection_name,
                    "estimated_count": after_count,
                },
                "evidence_refs": [
                    {
                        "type": "mongodb_collection",
                        "database": database_name,
                        "collection": collection_name,
                        "operation": operation,
                    }
                ],
            }
            sys.stdout.write(json.dumps(response_payload, ensure_ascii=False, separators=(",", ":")))
            return 0
        except PyMongoError as exc:
            raise RuntimeError(f"real MongoDB {operation} failed: {exc}") from exc
        finally:
            client.close()
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "MONGODB_CONNECTOR_FAILED",
                    "error_stage": "mongodb_connector_runtime",
                    "operator_message": str(exc),
                    "recovery_hint": "Check MongoDB URI, pymongo installation, target collection, and request schema.",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
