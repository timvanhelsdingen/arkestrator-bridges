---
name: scripting-patterns
description: "Unity C# Scripting Patterns patterns and best practices for unity"
metadata:
  program: unity
  category: bridge
  title: Unity C# Scripting Patterns
  keywords: ["unity", "scripting-patterns"]
  source: bridge-repo
---

# Unity C# Scripting Patterns

## File Apply — Writing Scripts via Bridge

The bridge applies C# scripts as file changes (not via `unity_json`). Write `.cs` files to the project using file apply, then call `refresh_assets` to compile.

### MonoBehaviour Lifecycle
```csharp
public class PlayerController : MonoBehaviour
{
    void Awake()       { /* Called once when object instantiates */ }
    void Start()       { /* Called once before first Update */ }
    void Update()      { /* Called every frame */ }
    void FixedUpdate() { /* Called every physics step — use for Rigidbody */ }
    void OnDestroy()   { /* Cleanup when object is destroyed */ }
    void OnEnable()    { /* Called when component is enabled */ }
    void OnDisable()   { /* Called when component is disabled */ }
}
```
- `Awake` runs before `Start` — use for self-initialization
- `Start` runs after all `Awake` calls — use for cross-object references
- `FixedUpdate` for physics, `Update` for input and rendering logic
- `LateUpdate` runs after all `Update` calls — use for camera follow

### Coroutines
```csharp
IEnumerator SpawnWave()
{
    for (int i = 0; i < 5; i++)
    {
        Instantiate(enemyPrefab, spawnPoint.position, Quaternion.identity);
        yield return new WaitForSeconds(0.5f);
    }
}
// Start with: StartCoroutine(SpawnWave());
// Stop with: StopCoroutine(...) or StopAllCoroutines();
```
- `yield return null` — wait one frame
- `yield return new WaitForSeconds(t)` — wait t seconds
- `yield return new WaitForFixedUpdate()` — wait for next physics step
- `yield return new WaitUntil(() => condition)` — wait until condition is true

### Events and Delegates
```csharp
// Define event
public static event Action<int> OnScoreChanged;

// Raise event
OnScoreChanged?.Invoke(newScore);

// Subscribe (in OnEnable) / Unsubscribe (in OnDisable)
GameManager.OnScoreChanged += HandleScoreChanged;
GameManager.OnScoreChanged -= HandleScoreChanged;
```
- Always unsubscribe in `OnDisable` or `OnDestroy` to prevent memory leaks
- Use `UnityEvent` for inspector-assignable callbacks

### ScriptableObjects
```csharp
[CreateAssetMenu(fileName = "NewWeaponData", menuName = "Game/Weapon Data")]
public class WeaponData : ScriptableObject
{
    public string weaponName;
    public int damage;
    public float fireRate;
    public GameObject projectilePrefab;
}
```
- Data containers that live as assets — shared across scenes
- Reference from MonoBehaviours via `[SerializeField] private WeaponData weaponData;`
- Changes persist in the asset, not per-instance

## Common C# Patterns

### Serialization
- `[SerializeField] private float speed;` — expose private field in Inspector
- `[HideInInspector] public float internalValue;` — hide public field from Inspector
- `[Header("Movement")]` — section header in Inspector
- `[Range(0f, 10f)]` — slider constraint
- `[Tooltip("Speed in m/s")]` — hover text

### Singleton Pattern
```csharp
public class GameManager : MonoBehaviour
{
    public static GameManager Instance { get; private set; }

    void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }
}
```

### Object Pooling
```csharp
private Queue<GameObject> pool = new Queue<GameObject>();

public GameObject Get()
{
    var obj = pool.Count > 0 ? pool.Dequeue() : Instantiate(prefab);
    obj.SetActive(true);
    return obj;
}

public void Return(GameObject obj)
{
    obj.SetActive(false);
    pool.Enqueue(obj);
}
```

## Script File Conventions
- One MonoBehaviour per file, filename matches class name
- Place in `Assets/Scripts/` organized by feature: `Player/`, `Enemy/`, `UI/`, `Managers/`
- Use namespaces for larger projects to avoid conflicts
- After writing a `.cs` file, always call `{"action": "refresh_assets"}` to trigger recompilation
