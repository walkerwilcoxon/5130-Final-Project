import json
import os
from datetime import datetime

FILE_NAME = "task_data.json"

def load_data():
    if not os.path.exists(FILE_NAME):
        return []
    try:
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_data(tasks):
    with open(FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def next_id(tasks):
    return max([t["id"] for t in tasks], default=0) + 1

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print("=" * 60)
    print(title.center(60))
    print("=" * 60)

def ask(prompt):
    return input(prompt).strip()

def ask_nonempty(prompt):
    while True:
        value = ask(prompt)
        if value:
            return value
        print("Value cannot be empty.")

def ask_priority(default=None):
    while True:
        prompt = "Priority [low/medium/high]"
        if default:
            prompt += f" ({default})"
        prompt += ": "
        value = ask(prompt).lower()
        if not value and default:
            return default
        if value in ("low", "medium", "high"):
            return value
        print("Invalid priority.")

def ask_date(prompt, default=None):
    while True:
        value = ask(prompt)
        if not value:
            return default if default is not None else ""
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            print("Use YYYY-MM-DD format.")

def format_task(task):
    done = "X" if task["done"] else " "
    due = task["due"] if task["due"] else "-"
    return f'[{done}] #{task["id"]:03d} {task["title"]} | {task["priority"]} | due {due}'

def list_tasks(tasks):
    header("ALL TASKS")
    if not tasks:
        print("No tasks available.")
        return
    for task in tasks:
        print(format_task(task))
        if task["notes"]:
            print("   notes:", task["notes"])
        print("   created:", task["created"])
        print("   updated:", task["updated"])

def add_task(tasks):
    header("ADD TASK")
    title = ask_nonempty("Title: ")
    notes = ask("Notes: ")
    priority = ask_priority()
    due = ask_date("Due date YYYY-MM-DD (optional): ")
    stamp = now()
    task = {
        "id": next_id(tasks),
        "title": title,
        "notes": notes,
        "priority": priority,
        "due": due,
        "done": False,
        "created": stamp,
        "updated": stamp,
    }
    tasks.append(task)
    save_data(tasks)
    print("Task added.")

def find_task(tasks, task_id):
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None

def ask_task_id():
    while True:
        raw = ask("Task ID: ")
        if raw.isdigit():
            return int(raw)
        print("Enter a numeric ID.")

def edit_task(tasks):
    header("EDIT TASK")
    task = find_task(tasks, ask_task_id())
    if not task:
        print("Task not found.")
        return
    title = ask(f'Title ({task["title"]}): ')
    notes = ask(f'Notes ({task["notes"]}): ')
    priority = ask_priority(task["priority"])
    due = ask_date(f'Due date ({task["due"] or "-"}) [blank keeps]: ', task["due"])
    if title:
        task["title"] = title
    if notes:
        task["notes"] = notes
    task["priority"] = priority
    task["due"] = due
    task["updated"] = now()
    save_data(tasks)
    print("Task updated.")

def toggle_done(tasks):
    header("TOGGLE DONE")
    task = find_task(tasks, ask_task_id())
    if not task:
        print("Task not found.")
        return
    task["done"] = not task["done"]
    task["updated"] = now()
    save_data(tasks)
    print("Task status changed.")

def delete_task(tasks):
    header("DELETE TASK")
    task = find_task(tasks, ask_task_id())
    if not task:
        print("Task not found.")
        return
    confirm = ask(f'Delete "{task["title"]}"? [y/N]: ').lower()
    if confirm == "y":
        tasks.remove(task)
        save_data(tasks)
        print("Task deleted.")
    else:
        print("Cancelled.")

def search_tasks(tasks):
    header("SEARCH TASKS")
    query = ask_nonempty("Search text: ").lower()
    results = []
    for task in tasks:
        text = (task["title"] + " " + task["notes"]).lower()
        if query in text:
            results.append(task)
    if not results:
        print("No matches.")
        return
    for task in results:
        print(format_task(task))

def sort_tasks(tasks):
    header("SORT TASKS")
    print("1. By ID")
    print("2. By title")
    print("3. By priority")
    print("4. By due date")
    choice = ask("Choice: ")
    rank = {"high": 0, "medium": 1, "low": 2}
    if choice == "1":
        tasks.sort(key=lambda t: t["id"])
    elif choice == "2":
        tasks.sort(key=lambda t: t["title"].lower())
    elif choice == "3":
        tasks.sort(key=lambda t: rank[t["priority"]])
    elif choice == "4":
        tasks.sort(key=lambda t: (t["due"] == "", t["due"]))
    else:
        print("Invalid choice.")
        return
    save_data(tasks)
    print("Tasks sorted.")

def show_stats(tasks):
    header("STATISTICS")
    total = len(tasks)
    done = sum(1 for t in tasks if t["done"])
    open_tasks = total - done
    today = datetime.now().strftime("%Y-%m-%d")
    overdue = sum(1 for t in tasks if t["due"] and t["due"] < today and not t["done"])
    print("Total   :", total)
    print("Open    :", open_tasks)
    print("Done    :", done)
    print("Overdue :", overdue)

def menu():
    header("TASK MANAGER")
    print("1. List tasks")
    print("2. Add task")
    print("3. Edit task")
    print("4. Toggle done")
    print("5. Delete task")
    print("6. Search tasks")
    print("7. Sort tasks")
    print("8. Statistics")
    print("0. Quit")

def main():
    tasks = load_data()
    while True:
        clear()
        menu()
        choice = ask("Select: ")
        clear()
        if choice == "1":
            list_tasks(tasks)
        elif choice == "2":
            add_task(tasks)
        elif choice == "3":
            edit_task(tasks)
        elif choice == "4":
            toggle_done(tasks)
        elif choice == "5":
            delete_task(tasks)
        elif choice == "6":
            search_tasks(tasks)
        elif choice == "7":
            sort_tasks(tasks)
        elif choice == "8":
            show_stats(tasks)
        elif choice == "0":
            print("Goodbye.")
            break
        else:
            print("Invalid option.")
        pause()

if __name__ == "__main__":
    main()