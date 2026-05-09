#ifndef ASSETKIT_BLENDER_MEM_H
#define ASSETKIT_BLENDER_MEM_H

#include <stddef.h>
#include <stdint.h>

#define AKB_ARENA_DEFAULT_BLOCK_SIZE (64u * 1024u)

typedef struct AkbArenaBlock AkbArenaBlock;

typedef struct AkbArena {
  AkbArenaBlock *blocks;
  size_t         default_block_size;
} AkbArena;

void
akb_arena_free(AkbArena *arena);

void *
akb_arena_alloc(AkbArena *arena, size_t size, size_t align);

void *
akb_owned_alloc(AkbArena *arena, size_t size, size_t align, uint8_t *arena_owned);

#endif
