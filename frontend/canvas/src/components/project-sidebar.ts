import type {
  ProjectController,
  ProjectControllerState,
} from "../controllers/project-controller";
import { canvasUserMessage } from "../domain/user-message";

export interface ProjectSidebar {
  element: HTMLElement;
  update(state: ProjectControllerState): void;
}

function actionButton(
  label: string,
  action: () => void,
  testId?: string,
): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (testId !== undefined) {
    button.dataset.testid = testId;
  }
  button.addEventListener("click", action);
  return button;
}

export function createProjectSidebar(controller: ProjectController): ProjectSidebar {
  let renamingProjectId: string | null = null;
  let latestState = controller.getState();
  const element = document.createElement("aside");
  element.className = "canvas-project-sidebar";
  element.dataset.testid = "canvas-project-sidebar";
  element.setAttribute("aria-label", "项目列表");

  const header = document.createElement("header");
  header.className = "canvas-project-sidebar-header";
  const heading = document.createElement("h1");
  heading.textContent = "产品视觉画布";
  const projectCount = document.createElement("span");
  projectCount.className = "canvas-project-count";
  projectCount.dataset.testid = "canvas-project-count";
  header.append(heading, projectCount);

  const createSection = document.createElement("section");
  createSection.className = "canvas-project-create-section";
  const createHeading = document.createElement("h2");
  createHeading.textContent = "新建项目";
  const createForm = document.createElement("form");
  createForm.className = "canvas-create-project";
  const createInput = document.createElement("input");
  createInput.type = "text";
  createInput.required = true;
  createInput.maxLength = 200;
  createInput.setAttribute("aria-label", "新建项目名称");
  createInput.dataset.testid = "canvas-project-create-name";
  createInput.placeholder = "项目名称";
  const createButton = document.createElement("button");
  createButton.type = "submit";
  createButton.textContent = "新建";
  createButton.disabled = true;
  createButton.dataset.testid = "canvas-project-create";
  createForm.append(createInput, createButton);
  createInput.addEventListener("input", () => {
    createButton.disabled = createInput.value.trim() === "";
  });
  createForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const name = createInput.value.trim();
    if (name !== "") {
      void controller.createProject(name).then((result) => {
        if (result.ok) {
          createInput.value = "";
          createButton.disabled = true;
        }
      });
    }
  });
  createSection.append(createHeading, createForm);

  const filterSection = document.createElement("section");
  filterSection.className = "canvas-project-filter-section";
  const filterHeading = document.createElement("h2");
  filterHeading.textContent = "查找项目";
  const search = document.createElement("input");
  search.type = "search";
  search.setAttribute("aria-label", "搜索项目");
  search.dataset.testid = "canvas-project-search";
  search.placeholder = "搜索项目";
  const archivedLabel = document.createElement("label");
  archivedLabel.className = "canvas-project-archived-filter";
  const archived = document.createElement("input");
  archived.type = "checkbox";
  archivedLabel.append(archived, "显示已归档");
  search.addEventListener("input", () => {
    void controller.searchProjects(search.value, archived.checked);
  });
  archived.addEventListener("change", () => {
    void controller.searchProjects(search.value, archived.checked);
  });
  filterSection.append(filterHeading, search, archivedLabel);

  const listSection = document.createElement("section");
  listSection.className = "canvas-project-list-section";
  const listHeading = document.createElement("h2");
  listHeading.textContent = "项目";
  const list = document.createElement("ul");
  list.className = "canvas-project-list";
  list.dataset.testid = "canvas-project-list";
  const feedback = document.createElement("p");
  feedback.className = "canvas-project-feedback";
  feedback.setAttribute("aria-live", "polite");
  const dialogs = document.createElement("div");
  dialogs.className = "canvas-project-dialogs";
  listSection.append(listHeading, feedback, list);
  element.append(header, createSection, filterSection, listSection, dialogs);

  const update = (state: ProjectControllerState): void => {
    latestState = state;
    if (document.activeElement !== search) {
      search.value = state.query;
    }
    archived.checked = state.includeArchived;
    projectCount.textContent = `${state.projects.length} 个项目`;
    feedback.textContent = state.loading ? "正在加载项目…" : state.error === null ? "" : canvasUserMessage(state.error, "项目加载失败，请重试");
    list.replaceChildren();
    if (!state.loading && state.error === null && state.projects.length === 0) {
      const empty = document.createElement("li");
      empty.className = "canvas-project-empty";
      empty.dataset.testid = "canvas-project-empty";
      const emptyTitle = document.createElement("strong");
      emptyTitle.textContent = state.query.trim() === "" ? "还没有项目" : "没有找到匹配项目";
      const emptyCopy = document.createElement("span");
      emptyCopy.textContent = state.query.trim() === ""
        ? "在上方输入名称，创建第一个产品项目。"
        : "换个关键词，或勾选显示已归档项目。";
      empty.append(emptyTitle, emptyCopy);
      list.append(empty);
    }
    for (const project of state.projects) {
      const row = document.createElement("li");
      row.className = "canvas-project-row";
      row.dataset.testid = "canvas-project-row";
      row.dataset.projectId = project.id;
      if (project.id === state.activeProjectId) {
        row.classList.add("is-active");
      }
      const select = actionButton(project.name, () => {
        if (project.id !== state.activeProjectId) void controller.switchProject(project.id);
      }, "canvas-project-switch");
      select.className = "canvas-project-select";
      if (project.id === state.activeProjectId) select.setAttribute("aria-current", "true");
      const meta = document.createElement("span");
      meta.className = "canvas-project-meta";
      meta.textContent = project.status === "archived" ? "可恢复" : "自动保存";
      const status = document.createElement("span");
      status.className = "canvas-project-status";
      status.textContent = project.id === state.activeProjectId
        ? "当前"
        : project.status === "archived"
          ? "已归档"
          : "项目";
      row.append(select, status, meta);

      if (project.id === state.activeProjectId && renamingProjectId === project.id) {
        const renameForm = document.createElement("form");
        renameForm.className = "canvas-project-rename-form";
        const rename = document.createElement("input");
        rename.type = "text";
        rename.value = project.name;
        rename.maxLength = 200;
        rename.setAttribute("aria-label", `重命名 ${project.name}`);
        rename.dataset.testid = "canvas-project-rename";
        const saveRename = actionButton("保存", () => {
            const name = rename.value.trim();
            if (name !== "") {
              void controller.renameActiveProject(name).then((result) => {
                if (result.ok) {
                  renamingProjectId = null;
                  update(latestState);
                }
              });
            }
          }, "canvas-project-rename-save");
        const cancelRename = actionButton("取消", () => {
          renamingProjectId = null;
          update(latestState);
        });
        renameForm.append(rename, saveRename, cancelRename);
        renameForm.addEventListener("submit", (event) => {
          event.preventDefault();
          saveRename.click();
        });
        row.append(renameForm);
        queueMicrotask(() => rename.select());
      }

      const actions = document.createElement("details");
      actions.className = "canvas-project-menu";
      const summary = document.createElement("summary");
      summary.textContent = "更多";
      summary.setAttribute("aria-label", `${project.name}项目操作`);
      const menu = document.createElement("div");
      menu.className = "canvas-project-menu-popover";
      menu.setAttribute("role", "menu");
      if (project.id === state.activeProjectId && renamingProjectId !== project.id) {
        menu.append(actionButton("重命名", () => {
          renamingProjectId = project.id;
          actions.open = false;
          update(latestState);
        }, "canvas-project-rename-start"));
      }
      if (project.status === "archived") {
        menu.append(actionButton("恢复项目", () => void controller.restoreProject(project.id), "canvas-project-restore"));
      } else if (project.status === "active") {
        menu.append(actionButton("归档项目", () => void controller.archiveProject(project.id), "canvas-project-archive"));
      }
      const remove = actionButton("删除项目", () => controller.requestDeleteProject(project.id), "canvas-project-delete");
      remove.className = "is-danger";
      menu.append(remove);
      actions.append(summary, menu);
      row.append(actions);
      list.append(row);
    }

    dialogs.replaceChildren();
    if (state.deleteCandidateId !== null) {
      const dialog = document.createElement("section");
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("aria-label", "确认删除项目");
      dialog.dataset.testid = "canvas-delete-confirm";
      const copy = document.createElement("p");
      copy.textContent = "删除后项目与其画布数据将被永久移除。";
      dialog.append(
        copy,
        actionButton("确认删除", () => void controller.confirmDeleteProject(), "canvas-delete-confirm-submit"),
        actionButton("取消", () => controller.cancelDeleteProject(), "canvas-delete-confirm-cancel"),
      );
      dialogs.append(dialog);
    }
    if (state.pendingSwitch !== null) {
      const dialog = document.createElement("section");
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("aria-label", "未保存项目切换");
      dialog.dataset.testid = "canvas-switch-decision";
      const copy = document.createElement("p");
      copy.textContent = "当前项目保存失败。请选择重试、留在当前项目或放弃更改。";
      dialog.append(
        copy,
        actionButton("重试", () => void controller.retrySwitch(), "canvas-switch-retry"),
        actionButton("留在当前项目", () => controller.stayOnProject(), "canvas-switch-stay"),
        actionButton("放弃更改并切换", () => void controller.discardAndSwitch(), "canvas-switch-discard"),
      );
      dialogs.append(dialog);
    }
  };

  return { element, update };
}
