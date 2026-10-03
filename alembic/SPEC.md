# Alembic SPEC

数据库结构只通过 Alembic 版本演进。Revision 不读取 Vault 文档、不写业务数据、不删除表；SQLite 数据文件路径由 CLI 在运行时注入。
