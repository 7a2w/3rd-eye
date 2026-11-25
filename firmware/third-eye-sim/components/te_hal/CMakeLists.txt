if(CONFIG_TE_PLATFORM_XIAO)
    set(srcs src/xiao/xiao_core.c src/xiao/xiao_cam.c src/xiao/xiao_mic.c src/xiao/xiao_sd.c
             src/xiao/xiao_ble.c src/xiao/xiao_wifi.c)
else()
    set(srcs src/sim/sim_core.c src/sim/sim_cam.c src/sim/sim_mic.c src/sim/sim_sd.c src/sim/sim_link.c)
endif()

# ESP-IDF resolves component requirements before Kconfig values are known,
# so both platforms' requirements are listed; the linker drops what is unused.
idf_component_register(SRCS ${srcs}
                       INCLUDE_DIRS include
                       PRIV_REQUIRES esp_driver_gpio esp_driver_i2s esp_driver_tsens esp_adc esp_driver_sdmmc
                                     fatfs sdmmc esp_wifi esp_netif esp_event lwip bt nvs_flash esp_timer
                                     esp_psram esp_eth esp_partition espressif__esp32-camera)
