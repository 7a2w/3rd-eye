idf_component_register(SRCS app_main.c ctrl.c capture.c storage.c link.c xfer.c metrics.c adpcm.c util.c
                       INCLUDE_DIRS .
                       PRIV_REQUIRES te_hal esp_timer esp_psram fatfs vfs esp_rom esp_ringbuf spi_flash)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-format-truncation)
