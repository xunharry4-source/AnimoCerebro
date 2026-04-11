# 统一数据库连接使用指南

**模块**: `zentex.common.db_connection`  
**版本**: 1.0.0  
**最后更新**: 2026-04-11

---

## 📋 概述

`UnifiedDatabaseConnection` 提供了 Zentex 应用的统一数据库连接管理，确保整个应用使用同一个 SQLite 连接实例。

### 核心特性

✅ **单例模式**: 全局唯一连接实例  
✅ **线程安全**: 每个线程独立的连接  
✅ **WAL 模式**: 支持并发读操作  
✅ **自动事务**: 上下文管理器自动提交/回滚  
✅ **FastAPI 集成**: 提供依赖注入函数  

---

## 🚀 快速开始

### 1. 基本用法

```python
from zentex.common.db_connection import get_db_connection

# 获取数据库连接单例
db = get_db_connection()

# 初始化（通常在应用启动时）
db.initialize("runtime/data/zentex_core.db")

# 执行查询
rows = db.execute_query("SELECT * FROM agents WHERE status = ?", ("ACTIVE",))

# 执行更新
affected = db.execute_update(
    "UPDATE agents SET status = ? WHERE agent_id = ?",
    ("INACTIVE", "agent-123")
)

# 执行标量查询
count = db.execute_scalar("SELECT COUNT(*) FROM agents")
```

### 2. FastAPI 依赖注入

```python
from fastapi import FastAPI, Depends, APIRouter
from zentex.common.db_connection import get_db_dependency

app = FastAPI()
router = APIRouter()

@router.get("/agents")
def list_agents(db = Depends(get_db_dependency)):
    """List all agents from database."""
    rows = db.execute_query("SELECT * FROM agents")
    return [dict(row) for row in rows]

@router.post("/agents")
def create_agent(agent_data: dict, db = Depends(get_db_dependency)):
    """Create a new agent."""
    db.execute_update(
        "INSERT INTO agents (agent_id, name, status) VALUES (?, ?, ?)",
        (agent_data['id'], agent_data['name'], 'ACTIVE')
    )
    return {"status": "created"}

app.include_router(router)
```

### 3. 事务管理

```python
from zentex.common.db_connection import get_db_connection

db = get_db_connection()

# 成功的事务 - 自动提交
try:
    with db.get_connection() as conn:
        conn.execute("INSERT INTO agents (...) VALUES (...)")
        conn.execute("INSERT INTO agent_audit_log (...) VALUES (...)")
    # 如果到这里没有异常，自动 commit
except Exception as e:
    # 如果发生异常，自动 rollback
    print(f"Transaction failed: {e}")

# 失败的事务 - 自动回滚
try:
    with db.get_connection() as conn:
        conn.execute("INSERT INTO agents (...) VALUES (...)")
        raise ValueError("Simulated error")  # 模拟错误
except ValueError:
    pass  # 数据已自动回滚
```

---

## 📚 API 参考

### UnifiedDatabaseConnection

#### 初始化

```python
def initialize(db_path: str, enable_wal: bool = True) -> None:
    """
    初始化数据库连接
    
    Args:
        db_path: SQLite 数据库文件路径
        enable_wal: 是否启用 WAL 模式（默认 True）
    """
```

#### 属性

```python
@property
def is_initialized(self) -> bool:
    """检查数据库是否已初始化"""

@property
def db_path(self) -> Optional[Path]:
    """获取数据库文件路径"""
```

#### 查询方法

```python
def execute_query(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    """
    执行 SELECT 查询
    
    Returns:
        sqlite3.Row 对象列表
    """

def execute_update(query: str, params: tuple = ()) -> int:
    """
    执行 INSERT/UPDATE/DELETE
    
    Returns:
        受影响的行数
    """

def execute_many(query: str, params_list: List[tuple]) -> int:
    """
    批量执行
    
    Returns:
        总受影响行数
    """

def execute_scalar(query: str, params: tuple = ()) -> Any:
    """
    执行返回单个值的查询
    
    Returns:
        单个值或 None
    """

def execute_script(sql_script: str) -> None:
    """执行 SQL 脚本（多条语句）"""
```

#### 工具方法

```python
def table_exists(table_name: str) -> bool:
    """检查表是否存在"""

def get_table_names() -> List[str]:
    """获取所有表名"""

def shutdown() -> None:
    """关闭数据库连接并清理资源"""
```

#### 上下文管理器

```python
@contextmanager
def get_connection():
    """
    获取数据库连接的上下文管理器
    
    自动处理事务提交和回滚
    
    Example:
        with db.get_connection() as conn:
            conn.execute("INSERT ...")
            # 成功则自动 commit，失败则自动 rollback
    """
```

---

## 🔧 高级用法

### 1. 与 DAO 层集成

```python
from zentex.common.db_connection import get_db_connection
from zentex.common.database import LRUCache, BaseDAO

class AgentDAO(BaseDAO):
    def __init__(self, cache_size: int = 500, cache_ttl: int = 300):
        # 使用统一连接
        db = get_db_connection()
        cache = LRUCache(max_size=cache_size, ttl_seconds=cache_ttl)
        super().__init__(db, cache)
        self.table_name = "agents"

# 使用
dao = AgentDAO()
agents = dao.list_agents(status="ACTIVE")
```

### 2. 自定义连接配置

```python
from zentex.common.db_connection import get_db_connection

db = get_db_connection()
db.initialize(
    "runtime/data/zentex_core.db",
    enable_wal=True  # 启用 WAL 模式
)

# 手动配置 PRAGMA
with db.get_connection() as conn:
    conn.execute("PRAGMA journal_size_limit=67108864")  # 64MB
    conn.execute("PRAGMA mmap_size=268435456")  # 256MB
```

### 3. 批量操作优化

```python
# 批量插入大量数据
db = get_db_connection()

agents_data = [
    (f"agent-{i}", f"Agent {i}", "ACTIVE")
    for i in range(1000)
]

affected = db.execute_many(
    "INSERT INTO agents (agent_id, name, status) VALUES (?, ?, ?)",
    agents_data
)
print(f"Inserted {affected} agents")
```

### 4. 复杂查询

```python
# 使用子查询
result = db.execute_query("""
    SELECT a.*, COUNT(t.task_id) as task_count
    FROM agents a
    LEFT JOIN task_agent_mapping t ON a.agent_id = t.agent_id
    WHERE a.status = ?
    GROUP BY a.agent_id
    ORDER BY task_count DESC
    LIMIT ?
""", ("ACTIVE", 10))

# 使用视图
stats = db.execute_query("SELECT * FROM v_agent_full_info WHERE status = ?", ("ACTIVE",))
```

---

## ⚠️ 注意事项

### 1. 初始化时机

**正确**: 在应用启动时初始化
```python
# web_dev.py 或 main.py
from zentex.common.db_connection import get_db_connection

def startup():
    db = get_db_connection()
    db.initialize("runtime/data/zentex_core.db")
```

**错误**: 每次请求都初始化
```python
# ❌ 不要这样做
@app.get("/agents")
def list_agents():
    db = get_db_connection()
    db.initialize("...")  # 重复初始化
```

### 2. 线程安全

```python
# ✅ 线程安全 - 每个线程有独立连接
import threading

def worker():
    db = get_db_connection()
    # 每个线程有自己的连接
    db.execute_query("SELECT ...")

threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads:
    t.start()
```

### 3. 事务隔离

```python
# ✅ 使用上下文管理器确保事务完整性
with db.get_connection() as conn:
    conn.execute("INSERT INTO agents ...")
    conn.execute("INSERT INTO audit_log ...")
    # 两者要么都成功，要么都失败

# ❌ 避免手动管理事务
conn = db._get_connection()
conn.execute("INSERT ...")
conn.commit()  # 容易忘记或出错
```

### 4. 资源清理

```python
# 应用关闭时清理
import atexit
from zentex.common.db_connection import get_db_connection

def shutdown():
    db = get_db_connection()
    db.shutdown()

atexit.register(shutdown)
```

---

## 🧪 测试示例

```python
import pytest
from zentex.common.db_connection import get_db_connection

@pytest.fixture
def db():
    """Test database fixture."""
    db = get_db_connection()
    db.initialize("runtime/data/test.db")
    
    # Create test tables
    db.execute_script("""
        CREATE TABLE test_items (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
    """)
    
    yield db
    
    # Cleanup
    db.shutdown()

def test_insert_and_query(db):
    """Test basic insert and query."""
    db.execute_update(
        "INSERT INTO test_items (name) VALUES (?)",
        ("test_item",)
    )
    
    rows = db.execute_query("SELECT * FROM test_items")
    assert len(rows) == 1
    assert rows[0]['name'] == "test_item"

def test_transaction_rollback(db):
    """Test transaction rollback on error."""
    try:
        with db.get_connection() as conn:
            conn.execute("INSERT INTO test_items (name) VALUES (?)", ("item1",))
            raise ValueError("Simulated error")
    except ValueError:
        pass
    
    # Should be rolled back
    count = db.execute_scalar("SELECT COUNT(*) FROM test_items")
    assert count == 0
```

---

## 📊 性能优化建议

### 1. 启用 WAL 模式

```python
db.initialize("runtime/data/zentex_core.db", enable_wal=True)
```

**效果**: 
- 允许多个读者同时访问
- 写操作不阻塞读操作
- 适合读多写少的场景

### 2. 调整缓存大小

```python
with db.get_connection() as conn:
    conn.execute("PRAGMA cache_size=-64000")  # 64MB
```

### 3. 批量操作

```python
# ✅ 批量插入（快）
db.execute_many("INSERT INTO ... VALUES (...)", data_list)

# ❌ 逐条插入（慢）
for item in data_list:
    db.execute_update("INSERT INTO ... VALUES (...)", item)
```

### 4. 使用索引

```sql
-- 为常用查询字段创建索引
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_updated ON agents(updated_at);
```

---

## 🔍 故障排查

### 问题 1: "Database not initialized"

**原因**: 在使用前未调用 `initialize()`

**解决**:
```python
db = get_db_connection()
if not db.is_initialized:
    db.initialize("runtime/data/zentex_core.db")
```

### 问题 2: "database is locked"

**原因**: 多个写操作并发

**解决**:
- 启用 WAL 模式
- 减少并发写操作
- 增加超时时间

```python
db._local.connection = sqlite3.connect(..., timeout=60.0)
```

### 问题 3: 内存占用过高

**原因**: 缓存过大或连接未释放

**解决**:
```python
# 减小缓存
cache = LRUCache(max_size=500, ttl_seconds=120)

# 定期清理
db.shutdown()
```

---

## 📖 相关文档

- [数据库持久化进度报告](./DATABASE_PERSISTENCE_PROGRESS.md)
- [数据库实施总结](./DATABASE_IMPLEMENTATION_SUMMARY.md)
- [DAO 层使用指南](../common/database.py)

---

**维护者**: Zentex Development Team  
**联系方式**: dev@zentex.ai
