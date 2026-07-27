import createClient from "openapi-fetch";
import type { paths } from "./client";

const client = createClient<paths>({ baseUrl: "http://localhost:8000" });

// --- DOM ELEMENTS ---
const form = document.getElementById("userForm") as HTMLFormElement;
const userListContainer = document.getElementById("userList") as HTMLDivElement;
const searchButton = document.getElementById("searchBtn") as HTMLButtonElement;
const searchInput = document.getElementById("searchId") as HTMLInputElement;
const singleUserResult = document.getElementById("singleUserView") as HTMLDivElement;

// NEW: Edit Layout DOM Elements
const editSection = document.getElementById("editSection") as HTMLDivElement;
const editForm = document.getElementById("editForm") as HTMLFormElement;
const editUserIdInput = document.getElementById("editUserId") as HTMLInputElement;
const editUsernameInput = document.getElementById("editUsername") as HTMLInputElement;
const editAverageInput = document.getElementById("editAverage") as HTMLInputElement;
const cancelEditButton = document.getElementById("cancelEditBtn") as HTMLButtonElement;

// --- Helper: Open and Populate Edit Form ---
function startEdit(user: { id: number; username: string; average: number }) {
  editUserIdInput.value = user.id.toString();
  editUsernameInput.value = user.username;
  editAverageInput.value = user.average.toString();
  editSection.style.display = "block";
  editUsernameInput.focus();
}

// --- 1. FETCH ALL USERS ---
async function loadAllUsers() {
  userListContainer.innerHTML = "Loading users...";
  const { data, error } = await client.GET("/api/users");

  if (error) {
    userListContainer.innerHTML = "<p>No users found in the database.</p>";
    return;
  }

  userListContainer.innerHTML = "";
  data.forEach((user) => {
    const userCard = document.createElement("div");
    userCard.style.borderBottom = "1px solid #eee";
    userCard.style.padding = "8px 0";
    userCard.style.display = "flex";
    userCard.style.justifyContent = "space-between";
    userCard.style.alignItems = "center";

    // UPDATED: Injected an Edit button right next to the Delete button
    userCard.innerHTML = `
      <span><strong>ID:</strong> ${user.id} | <strong>Name:</strong> ${user.username} | <strong>Avg:</strong> ${user.average}</span>
      <div style="display: flex; gap: 5px;">
        <button class="edit-btn" data-id="${user.id}" data-username="${user.username}" data-average="${user.average}" style="background-color: #28a745; padding: 4px 8px; font-size: 12px; color: white; border: none; border-radius: 4px; cursor: pointer;">Edit</button>
        <button class="delete-btn" data-id="${user.id}" style="background-color: #ff4d4f; padding: 4px 8px; font-size: 12px; color: white; border: none; border-radius: 4px; cursor: pointer;">Delete</button>
      </div>
    `;
    userListContainer.appendChild(userCard);
  });

  // Bind Listeners to dynamic Edit buttons
  const editButtons = document.querySelectorAll(".edit-btn");
  editButtons.forEach((button) => {
    button.addEventListener("click", (e) => {
      const target = e.target as HTMLButtonElement;
      const id = parseInt(target.getAttribute("data-id") || "");
      const username = target.getAttribute("data-username") || "";
      const average = parseFloat(target.getAttribute("data-average") || "0");
      
      if (!isNaN(id)) {
        startEdit({ id, username, average });
      }
    });
  });

  // Bind Listeners to dynamic Delete buttons
  const deleteButtons = document.querySelectorAll(".delete-btn");
  deleteButtons.forEach((button) => {
    button.addEventListener("click", async (e) => {
      const target = e.target as HTMLButtonElement;
      const idToDelete = parseInt(target.getAttribute("data-id") || "");
      if (!isNaN(idToDelete)) {
        await deleteUser(idToDelete);
      }
    });
  });
}

// --- 2. DELETE USER ACTION ---
async function deleteUser(id: number) {
  if (!confirm(`Are you sure you want to delete user ID ${id}?`)) return;

  const { data, error } = await client.DELETE("/api/users/delete/{user_id}", {
    params: {
      path: { user_id: id },
    },
  });

  if (error) {
    alert(`Failed to delete user: ${error.detail || "Unknown error"}`);
    return;
  }

  alert(`Successfully removed user: ${data.username}`);
  loadAllUsers();
}

// --- 3. FETCH SINGLE USER BY ID ---
searchButton.addEventListener("click", async () => {
  const userId = parseInt(searchInput.value);
  if (isNaN(userId)) return alert("Please enter a valid numeric ID");

  singleUserResult.innerHTML = "Searching...";

  const { data, error } = await client.GET("/api/users/{user_id}", {
    params: {
      path: { user_id: userId },
    },
  });

  if (error) {
    singleUserResult.innerHTML = `<p style="color: red;">Error: ${error.detail || "User not found"}</p>`;
    return;
  }

  singleUserResult.innerHTML = `
    <div style="background: #e6f7ff; padding: 10px; border-radius: 4px; margin-top: 5px;">
      <strong>Found User:</strong> ${data.username} (Score: ${data.average})
    </div>
  `;
});

// --- 4. CREATE USER (FORM SUBMIT) ---
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const usernameInput = document.getElementById("username") as HTMLInputElement;
  const averageInput = document.getElementById("average") as HTMLInputElement;

  const { data, error } = await client.POST("/api/users/createuser", {
    body: {
      username: usernameInput.value,
      average: parseFloat(averageInput.value),
      nickname: null,
      parent: null
    },
  });

  if (error) {
    alert("Error saving user!");
    return;
  }

  alert(`Success! Saved user: ${data.username}`);
  form.reset();
  loadAllUsers();
});

// --- NEW: 5. SAVE EDITED USER (FORM SUBMIT PUT ROUTE) ---
editForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  
  const userId = parseInt(editUserIdInput.value, 10);

  const { data, error } = await client.PUT("/api/users/updateuser/{user_id}", {
    params: {
      path: { user_id: userId },
    },
    body: {
      // Satisfies UserUpdateModel contract without sending an explicit ID property inside JSON
      username: editUsernameInput.value,
      average: parseFloat(editAverageInput.value),
      nickname: null,
      parent: null,
    },
  });

  if (error) {
    alert("Error updating user!");
    return;
  }

  alert(`Success! Updated user: ${data.username}`);
  editForm.reset();
  editSection.style.display = "none";
  loadAllUsers(); // Instantly refresh table with accurate data state
});

// --- NEW: 6. CANCEL EDIT ACTION ---
cancelEditButton.addEventListener("click", () => {
  editForm.reset();
  editSection.style.display = "none";
});

// Initial load
loadAllUsers();