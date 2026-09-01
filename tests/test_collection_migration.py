import sqlite3
from pathlib import Path
from alembic import command
from alembic.config import Config

def cfg(path):
 c=Config(str((Path(__file__).parents[1]/'alembic.ini').resolve())); c.set_main_option('sqlalchemy.url',f'sqlite:///{path.as_posix()}'); return c

def test_legacy_collection_is_preserved(tmp_path):
 p=tmp_path/'c.db'; x=sqlite3.connect(p); x.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY,bupt_username TEXT); CREATE TABLE collection_settings (id INTEGER PRIMARY KEY,area_id TEXT,building_id TEXT,building_name TEXT,floor_id TEXT,floor_name TEXT,room_id TEXT,room_name TEXT,enabled BOOLEAN,status TEXT,message TEXT,last_attempt_time DATETIME,last_success_time DATETIME,last_source_time DATETIME); INSERT INTO collection_settings VALUES(1,'2','b','B','f','F','r','R',1,'success','legacy',NULL,NULL,NULL);"); x.commit();x.close(); command.upgrade(cfg(p),'head'); x=sqlite3.connect(p); assert x.execute('SELECT room_id FROM collection_settings_legacy_unassigned').fetchone()==('r',); assert x.execute('SELECT count(*) FROM collection_settings').fetchone()==(0,); x.close()

def test_legacy_alerts_are_preserved(tmp_path):
 p=tmp_path/'a.db'; x=sqlite3.connect(p); x.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY,bupt_username TEXT); CREATE TABLE alert_settings (id INTEGER PRIMARY KEY,enabled BOOLEAN,low_balance_enabled BOOLEAN,balance_warning_threshold FLOAT,balance_critical_threshold FLOAT,low_remaining_days_enabled BOOLEAN,remaining_days_warning_threshold FLOAT,remaining_days_critical_threshold FLOAT); CREATE TABLE alert_events (id INTEGER PRIMARY KEY,area_id TEXT,room_id TEXT,building_name TEXT,floor_name TEXT,room_name TEXT,alert_type TEXT,level TEXT,status TEXT,title TEXT,message TEXT,trigger_value FLOAT,threshold_value FLOAT,source_time DATETIME,first_triggered_at DATETIME,last_seen_at DATETIME,resolved_at DATETIME,created_at DATETIME,updated_at DATETIME); INSERT INTO alert_settings VALUES(1,1,1,20,10,1,7,3);");x.commit();x.close();command.upgrade(cfg(p),'head');x=sqlite3.connect(p);assert x.execute('SELECT balance_warning_threshold FROM alert_settings_legacy_unassigned').fetchone()==(20.0,);assert x.execute('SELECT count(*) FROM alert_settings').fetchone()==(0,);assert x.execute("SELECT name FROM sqlite_master WHERE name='alert_events_legacy_unassigned'").fetchone();x.close()
