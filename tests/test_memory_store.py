"""Memory Store — episodic + semantic 各一条"""
import os
from agent.memory.store import MemoryStore


class TestMemoryStore:
    def setup_method(self):
        self.store = MemoryStore()
        self.store.initialize(profile="test")

    def teardown_method(self):
        self.store.shutdown()
        db = self.store.db_path
        if os.path.exists(db):
            os.remove(db)

    def test_save_and_search_episode(self):
        self.store.save_episode("deploy flask app",
                                [{"desc": "step1"}, {"desc": "step2"}],
                                [], "success", "done")
        results = self.store.search_similar("deploy flask", k=1)
        assert len(results) >= 1
        assert "deploy" in results[0]["goal"]

    def test_remember_and_search_semantic(self):
        self.store.remember_value("preference", "dark theme", source="test")
        r = self.store.search_semantic("dark theme")
        assert "dark theme" in r
        self.store.remember_value("preference", "light theme", source="test")
        r = self.store.search_semantic("preference")
        assert "light theme" in r
