import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { MinorCatalogItem, MinorPrefs, User } from "../types";
import type { SearchOverride } from "./useCatalogSearch";

interface Options {
  user: User;
  minorPrefs: MinorPrefs;
  setMinorPrefs: (next: MinorPrefs) => void;
  minorCategories: string[];
  setMinorCategories: (next: string[]) => void;
  minorsCatalog: MinorCatalogItem[];
  hasNonMinorSearchCriteria: () => boolean;
  executeSearch: (override?: SearchOverride) => Promise<void>;
  clearSearchResults: () => void;
  onExpandMinorPanel?: () => void;
  onUserUpdated?: (user: User) => void;
  onError?: (msg: string) => void;
}

export function resolveUserMinorPrefs(u: User): MinorPrefs {
  const mp = u.minor_prefs;
  return {
    selected_minor: mp?.selected_minor || "",
    versions: { ...(mp?.versions || {}) },
    colleges: { ...(mp?.colleges || {}) },
    completed_categories: { ...(mp?.completed_categories || {}) },
    hide_completed: mp?.hide_completed ?? true,
  };
}

export function useMinorPrefsController({
  minorPrefs,
  setMinorPrefs,
  minorCategories,
  setMinorCategories,
  minorsCatalog,
  hasNonMinorSearchCriteria,
  executeSearch,
  clearSearchResults,
  onExpandMinorPanel,
  onUserUpdated,
  onError,
}: Options) {
  const [savingMinorPrefs, setSavingMinorPrefs] = useState(false);

  const persistMinorPrefs = useCallback(
    async (next: MinorPrefs) => {
      setMinorPrefs(next);
      setSavingMinorPrefs(true);
      try {
        const res = await api.updateUserPreferences({ minor_prefs: next });
        onUserUpdated?.(res.user);
      } catch (err) {
        onError?.(err instanceof Error ? err.message : "Failed to save minor preference");
      } finally {
        setSavingMinorPrefs(false);
      }
    },
    [setMinorPrefs, onUserUpdated, onError]
  );

  const handleSelectMinor = useCallback(
    (minorId: string) => {
      setMinorCategories([]);
      const defVer = minorsCatalog.find((m) => m.id === minorId)?.default_version || "";
      const nextVer = minorId ? minorPrefs.versions[minorId] || defVer : "";
      const nextPrefs: MinorPrefs = {
        ...minorPrefs,
        selected_minor: minorId,
        versions: minorId ? { ...minorPrefs.versions, [minorId]: nextVer } : minorPrefs.versions,
      };
      void persistMinorPrefs(nextPrefs);

      if (minorId) {
        onExpandMinorPanel?.();
        void executeSearch({
          minor: minorId,
          minorVersion: nextVer,
          minorCategories: [],
          minorCompleted: nextPrefs.completed_categories[minorId] || [],
          minorHideCompleted: nextPrefs.hide_completed,
        });
      } else if (hasNonMinorSearchCriteria()) {
        void executeSearch({
          minor: "",
          minorVersion: "",
          minorCategories: [],
          minorCompleted: [],
        });
      } else {
        clearSearchResults();
      }
    },
    [
      minorsCatalog,
      minorPrefs,
      setMinorCategories,
      persistMinorPrefs,
      onExpandMinorPanel,
      executeSearch,
      hasNonMinorSearchCriteria,
      clearSearchResults,
    ]
  );

  const handleSelectMinorVersion = useCallback(
    (versionId: string) => {
      const mId = minorPrefs.selected_minor;
      if (!mId) return;
      setMinorCategories([]);
      const nextPrefs: MinorPrefs = {
        ...minorPrefs,
        versions: { ...minorPrefs.versions, [mId]: versionId },
      };
      void persistMinorPrefs(nextPrefs);
      void executeSearch({
        minor: mId,
        minorVersion: versionId,
        minorCategories: [],
        minorCompleted: nextPrefs.completed_categories[mId] || [],
        minorHideCompleted: nextPrefs.hide_completed,
      });
    },
    [minorPrefs, setMinorCategories, persistMinorPrefs, executeSearch]
  );

  const handleSelectMinorCollege = useCallback(
    (collegeId: string) => {
      const mId = minorPrefs.selected_minor;
      if (!mId) return;
      setMinorCategories([]);
      const nextPrefs: MinorPrefs = {
        ...minorPrefs,
        colleges: { ...(minorPrefs.colleges || {}), [mId]: collegeId },
      };
      void persistMinorPrefs(nextPrefs);
      void executeSearch({
        minor: mId,
        minorCollege: collegeId,
        minorCategories: [],
        minorCompleted: nextPrefs.completed_categories[mId] || [],
        minorHideCompleted: nextPrefs.hide_completed,
      });
    },
    [minorPrefs, setMinorCategories, persistMinorPrefs, executeSearch]
  );

  const handleToggleMinorFilterCategory = useCallback(
    (catId: string) => {
      const mId = minorPrefs.selected_minor;
      if (!mId) return;
      const exists = minorCategories.includes(catId);
      const nextCats = exists ? minorCategories.filter((c) => c !== catId) : [...minorCategories, catId];
      setMinorCategories(nextCats);
      void executeSearch({ minor: mId, minorCategories: nextCats });
    },
    [minorPrefs.selected_minor, minorCategories, setMinorCategories, executeSearch]
  );

  const handleClearMinorFilterCategories = useCallback(() => {
    setMinorCategories([]);
    if (minorPrefs.selected_minor) {
      void executeSearch({ minor: minorPrefs.selected_minor, minorCategories: [] });
    }
  }, [minorPrefs.selected_minor, setMinorCategories, executeSearch]);

  const handleToggleMinorCompletedCategory = useCallback(
    (catId: string) => {
      const mId = minorPrefs.selected_minor;
      if (!mId) return;
      const prevList = minorPrefs.completed_categories[mId] || [];
      const exists = prevList.includes(catId);
      const nextList = exists ? prevList.filter((c) => c !== catId) : [...prevList, catId];
      const nextPrefs: MinorPrefs = {
        ...minorPrefs,
        completed_categories: { ...minorPrefs.completed_categories, [mId]: nextList },
      };
      void persistMinorPrefs(nextPrefs);
      void executeSearch({
        minor: mId,
        minorCompleted: nextList,
        minorHideCompleted: nextPrefs.hide_completed,
      });
    },
    [minorPrefs, persistMinorPrefs, executeSearch]
  );

  const handleSetMinorHideCompleted = useCallback(
    (hide: boolean) => {
      const nextPrefs: MinorPrefs = { ...minorPrefs, hide_completed: hide };
      void persistMinorPrefs(nextPrefs);
      if (nextPrefs.selected_minor) {
        void executeSearch({ minor: nextPrefs.selected_minor, minorHideCompleted: hide });
      }
    },
    [minorPrefs, persistMinorPrefs, executeSearch]
  );

  const handleApplyMinorAutoFill = useCallback(
    (catIds: string[]) => {
      const mId = minorPrefs.selected_minor;
      if (!mId) return;
      const merged = Array.from(new Set([...(minorPrefs.completed_categories[mId] || []), ...catIds]));
      const nextPrefs: MinorPrefs = {
        ...minorPrefs,
        completed_categories: { ...minorPrefs.completed_categories, [mId]: merged },
      };
      void persistMinorPrefs(nextPrefs);
      void executeSearch({
        minor: mId,
        minorCompleted: merged,
        minorHideCompleted: nextPrefs.hide_completed,
      });
    },
    [minorPrefs, persistMinorPrefs, executeSearch]
  );

  const handleClearMinorCompleted = useCallback(() => {
    const mId = minorPrefs.selected_minor;
    if (!mId) return;
    const nextPrefs: MinorPrefs = {
      ...minorPrefs,
      completed_categories: { ...minorPrefs.completed_categories, [mId]: [] },
    };
    void persistMinorPrefs(nextPrefs);
    void executeSearch({
      minor: mId,
      minorCompleted: [],
      minorHideCompleted: nextPrefs.hide_completed,
    });
  }, [minorPrefs, persistMinorPrefs, executeSearch]);

  const clearSelectedMinorSilent = useCallback(() => {
    setMinorCategories([]);
    if (!minorPrefs.selected_minor) return;
    const nextPrefs: MinorPrefs = { ...minorPrefs, selected_minor: "" };
    void persistMinorPrefs(nextPrefs);
  }, [minorPrefs, setMinorCategories, persistMinorPrefs]);

  return {
    savingMinorPrefs,
    handleSelectMinor,
    handleSelectMinorVersion,
    handleSelectMinorCollege,
    handleToggleMinorFilterCategory,
    handleClearMinorFilterCategories,
    handleToggleMinorCompletedCategory,
    handleSetMinorHideCompleted,
    handleApplyMinorAutoFill,
    handleClearMinorCompleted,
    clearSelectedMinorSilent,
  };
}
