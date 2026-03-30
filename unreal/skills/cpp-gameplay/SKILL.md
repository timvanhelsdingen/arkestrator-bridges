---
name: cpp-gameplay
description: "C++ Gameplay Patterns patterns and best practices for unreal"
metadata:
  program: unreal
  category: bridge
  title: C++ Gameplay Patterns
  keywords: ["unreal", "cpp-gameplay"]
  source: bridge-repo
---

# Unreal C++ Gameplay Patterns

## Core UObject Hierarchy
- `UObject` — base class for all Unreal objects (GC managed, reflection, serialization)
- `AActor` — placeable in world, has transform, components, replication
- `APawn` — possessable by controller, movement input
- `ACharacter` — Pawn with CharacterMovementComponent, capsule, mesh
- `UActorComponent` — logic-only component (no transform)
- `USceneComponent` — component with transform, attachable
- `UPrimitiveComponent` — renderable/collidable (StaticMesh, SkeletalMesh)

## Property and Function Macros

### UPROPERTY Specifiers
```cpp
UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Combat")
float MaxHealth = 100.f;

UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
UStaticMeshComponent* MeshComp;

UPROPERTY(Replicated)
int32 Score;
```
- `EditAnywhere` — editable in defaults and instances
- `EditDefaultsOnly` — editable in class defaults only
- `EditInstanceOnly` — editable per-instance only
- `BlueprintReadWrite` / `BlueprintReadOnly` — Blueprint access
- `Replicated` / `ReplicatedUsing` — network replication
- `meta=(ClampMin, ClampMax)` — value range constraints

### UFUNCTION Specifiers
```cpp
UFUNCTION(BlueprintCallable, Category = "Combat")
void ApplyDamage(float Amount);

UFUNCTION(BlueprintImplementableEvent)
void OnDeath();

UFUNCTION(BlueprintNativeEvent)
void OnHit(const FHitResult& Hit);
void OnHit_Implementation(const FHitResult& Hit);

UFUNCTION(Server, Reliable)
void ServerFireWeapon();
```
- `BlueprintCallable` — callable from Blueprint
- `BlueprintPure` — no side effects, shown as value node
- `BlueprintImplementableEvent` — Blueprint provides implementation
- `BlueprintNativeEvent` — C++ default with Blueprint override
- `Server` / `Client` / `NetMulticast` — RPC replication

### UCLASS and USTRUCT
```cpp
UCLASS(Blueprintable, BlueprintType)
class MYGAME_API AMyActor : public AActor { ... };

USTRUCT(BlueprintType)
struct FItemData
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere) FString Name;
    UPROPERTY(EditAnywhere) int32 Value;
};
```

## Gameplay Framework Classes

### Core Framework
- `AGameModeBase` / `AGameMode` — server-side game rules, spawn logic, match state
- `AGameStateBase` / `AGameState` — replicated game state (scores, match phase)
- `APlayerController` — player input handling, HUD ownership, camera management
- `APlayerState` — replicated per-player data (name, score, team)
- `AHUD` — legacy HUD drawing (prefer UMG widgets)

### Typical Setup
```
GameMode → spawns → PlayerController → possesses → Pawn/Character
                  → creates → HUD/Widget
GameState → holds match-wide replicated data
PlayerState → holds per-player replicated data
```

## Component Patterns

### Creating Components in Constructor
```cpp
AMyActor::AMyActor()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));

    MeshComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
    MeshComp->SetupAttachment(RootComponent);

    BoxTrigger = CreateDefaultSubobject<UBoxComponent>(TEXT("Trigger"));
    BoxTrigger->SetupAttachment(RootComponent);
}
```

### Binding Delegates
```cpp
void AMyActor::BeginPlay()
{
    Super::BeginPlay();
    BoxTrigger->OnComponentBeginOverlap.AddDynamic(this, &AMyActor::OnOverlapBegin);
}
```

## Working with the Bridge
- Write C++ files via file apply to the project's `Source/` directory
- Use Python bridge commands for editor-time operations (spawning actors, setting properties)
- Use `unreal.EditorAssetLibrary` for asset operations
- Use `unreal.EditorLevelLibrary` for level actor operations
- Compile changes in-editor after applying C++ files (Hot Reload or Live Coding)

## Common Pitfalls
- Always call `Super::` in overridden lifecycle functions (BeginPlay, Tick, EndPlay)
- `GENERATED_BODY()` macro is mandatory in every UCLASS/USTRUCT
- Forward-declare in headers, include in .cpp to minimize compile times
- Use `TObjectPtr<>` for UPROPERTY object pointers in UE5
- Never store raw pointers to UObjects outside UPROPERTY — GC will collect them
- Use `TEXT("...")` macro for FName/FString literals for cross-platform consistency
