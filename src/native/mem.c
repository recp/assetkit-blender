#include "mem.h"

#include <stdlib.h>
#include <string.h>

struct AkbArenaBlock {
  struct AkbArenaBlock *next;
  size_t                used;
  size_t                capacity;
  unsigned char         data[];
};

static size_t
akb_align_up_size(size_t value, size_t align) {
  return (value + align - 1) & ~(align - 1);
}

void
akb_arena_free(AkbArena *arena) {
  AkbArenaBlock *block;
  AkbArenaBlock *next;

  if (!arena)
    return;

  for (block = arena->blocks; block; block = next) {
    next = block->next;
    free(block);
  }
  memset(arena, 0, sizeof(*arena));
}

void *
akb_arena_alloc(AkbArena *arena, size_t size, size_t align) {
  AkbArenaBlock *block;
  size_t default_size;
  size_t capacity;
  size_t offset;
  size_t used;
  uintptr_t base;
  uintptr_t ptr;

  if (!arena || size == 0)
    return NULL;

  if (align < sizeof(void *))
    align = sizeof(void *);
  if ((align & (align - 1)) != 0)
    align = sizeof(void *);

  block = arena->blocks;
  if (block) {
    base = (uintptr_t)block->data;
    ptr = (uintptr_t)akb_align_up_size((size_t)(base + block->used), align);
    offset = (size_t)(ptr - base);
    if (offset <= block->capacity && size <= block->capacity - offset) {
      block->used = offset + size;
      return (void *)ptr;
    }
  }

  default_size = arena->default_block_size
                 ? arena->default_block_size
                 : AKB_ARENA_DEFAULT_BLOCK_SIZE;
  if (size > SIZE_MAX - align)
    return NULL;
  capacity = size + align;
  if (capacity < default_size)
    capacity = default_size;
  if (capacity > SIZE_MAX - sizeof(*block))
    return NULL;

  block = (AkbArenaBlock *)malloc(sizeof(*block) + capacity);
  if (!block)
    return NULL;

  block->next = arena->blocks;
  block->used = 0;
  block->capacity = capacity;
  arena->blocks = block;

  base = (uintptr_t)block->data;
  ptr = (uintptr_t)akb_align_up_size((size_t)base, align);
  used = (size_t)(ptr - base) + size;
  if (used > block->capacity) {
    arena->blocks = block->next;
    free(block);
    return NULL;
  }

  block->used = used;
  return (void *)ptr;
}

void *
akb_owned_alloc(AkbArena *arena, size_t size, size_t align, uint8_t *arena_owned) {
  void *ptr;

  if (arena_owned)
    *arena_owned = 0;
  if (arena) {
    ptr = akb_arena_alloc(arena, size, align);
    if (!ptr)
      return NULL;
    if (arena_owned)
      *arena_owned = 1;
    return ptr;
  }

  return malloc(size);
}
