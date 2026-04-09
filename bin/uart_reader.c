/*
 * uart_reader.c
 * Đọc dữ liệu UART từ STM32 qua CP210x USB-UART trên Linux
 *
 * Format nhận:
 *   "1: <RPM_avg>\r\n"
 *   "2: <Temp_avg>\r\n"
 *
 * Build:  gcc uart_reader.c -o uart_reader
 * Run:    ./uart_reader /dev/ttyUSB0 115200
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <termios.h>
#include <time.h>
#include <signal.h>
/* ─── Cấu hình ─────────────────────────────────────────────── */
#define DEFAULT_PORT     "/dev/ttyUSB0"
#define DEFAULT_BAUDRATE 115200
#define READ_BUF_SIZE    256
#define LINE_BUF_SIZE    256

/* ─── Biến toàn cục ─────────────────────────────────────────── */
static volatile int running = 1;
static int uart_fd = -1;

/* ─── Xử lý Ctrl+C ──────────────────────────────────────────── */
void handle_sigint(int sig) {
    (void)sig;
    running = 0;
}

/* ─── Lấy timestamp hiện tại ────────────────────────────────── */
void get_timestamp(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    strftime(buf, len, "%H:%M:%S", t);
}

/* ─── Map baudrate số → hằng số termios ─────────────────────── */
speed_t get_baudrate(int baud) {
    switch (baud) {
        case 9600:   return B9600;
        case 19200:  return B19200;
        case 38400:  return B38400;
        case 57600:  return B57600;
        case 115200: return B115200;
        case 230400: return B230400;
        case 460800: return B460800;
        case 921600: return B921600;
        default:
            fprintf(stderr, "[WARN] Baudrate %d không được hỗ trợ, dùng 115200\n", baud);
            return B115200;
    }
}

/* ─── Mở và cấu hình cổng serial ────────────────────────────── */
int uart_open(const char *port, int baudrate) {
    int fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "[ERROR] Không mở được %s: %s\n", port, strerror(errno));
        return -1;
    }

    /* Đặt về blocking mode */
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);

    struct termios tty;
    memset(&tty, 0, sizeof(tty));

    if (tcgetattr(fd, &tty) != 0) {
        fprintf(stderr, "[ERROR] tcgetattr: %s\n", strerror(errno));
        close(fd);
        return -1;
    }

    speed_t speed = get_baudrate(baudrate);
    cfsetispeed(&tty, speed);
    cfsetospeed(&tty, speed);

    /* 8N1 - không dùng flow control */
    tty.c_cflag  =  (tty.c_cflag & ~CSIZE) | CS8; /* 8 data bits */
    tty.c_cflag &= ~PARENB;                        /* Không parity */
    tty.c_cflag &= ~CSTOPB;                        /* 1 stop bit */
    tty.c_cflag &= ~CRTSCTS;                       /* Không hardware flow */
    tty.c_cflag |=  CLOCAL | CREAD;                /* Bật nhận */

    tty.c_iflag &= ~(IXON | IXOFF | IXANY);        /* Không software flow */
    tty.c_iflag &= ~(IGNBRK | BRKINT | PARMRK |
                     ISTRIP | INLCR | IGNCR | ICRNL);

    tty.c_lflag  = 0;                               /* Raw mode */
    tty.c_oflag  = 0;

    /* Timeout: đọc block tối đa 1s nếu không có data */
    tty.c_cc[VMIN]  = 0;
    tty.c_cc[VTIME] = 10; /* 10 × 0.1s = 1 giây */

    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        fprintf(stderr, "[ERROR] tcsetattr: %s\n", strerror(errno));
        close(fd);
        return -1;
    }

    tcflush(fd, TCIFLUSH); /* Xóa buffer cũ */
    return fd;
}

/* ─── Parse một dòng "1: 3200" hoặc "2: 85" ─────────────────── */
int parse_line(const char *line, int *kind, int *value) {
    /* Bỏ whitespace đầu/cuối */
    while (*line == ' ' || *line == '\t') line++;

    if ((line[0] == '1' || line[0] == '2') &&
         line[1] == ':' && line[2] == ' ') {
        *kind  = line[0] - '0';
        *value = atoi(line + 3);
        return 1;
    }
    return 0;
}

/* ─── Main ───────────────────────────────────────────────────── */
int main(int argc, char *argv[]) {
    const char *port     = (argc >= 2) ? argv[1] : DEFAULT_PORT;
    int         baudrate = (argc >= 3) ? atoi(argv[2]) : DEFAULT_BAUDRATE;

    signal(SIGINT, handle_sigint);

    printf("================================================\n");
    printf("  UART Logger — STM32 Engine Monitor\n");
    printf("  Cổng: %-20s Baud: %d\n", port, baudrate);
    printf("  Nhấn Ctrl+C để dừng\n");
    printf("================================================\n\n");

    uart_fd = uart_open(port, baudrate);
    if (uart_fd < 0) return EXIT_FAILURE;

    printf("[OK] Đã kết nối %s @ %d baud\n\n", port, baudrate);

    /* Buffer tích lũy để tách dòng */
    char line_buf[LINE_BUF_SIZE];
    int  line_pos = 0;

    char read_buf[READ_BUF_SIZE];
    char timestamp[16];

    int rpm_val  = -1;
    int temp_val = -1;

    while (running) {
        ssize_t n = read(uart_fd, read_buf, sizeof(read_buf) - 1);

        if (n < 0) {
            if (errno == EINTR) continue;
            fprintf(stderr, "[ERROR] read: %s\n", strerror(errno));
            break;
        }

        if (n == 0) {
            /* Timeout — không có data */
            continue;
        }

        /* Xử lý từng byte, tách theo '\n' */
        for (ssize_t i = 0; i < n; i++) {
            char c = read_buf[i];

            if (c == '\r') continue; /* Bỏ CR */

            if (c == '\n') {
                /* Kết thúc một dòng */
                line_buf[line_pos] = '\0';
                line_pos = 0;

                if (strlen(line_buf) == 0) continue;

                int kind, value;
                if (parse_line(line_buf, &kind, &value)) {
                    get_timestamp(timestamp, sizeof(timestamp));

                    if (kind == 1) {
                        rpm_val = value;
                        printf("[%s] RPM   : %5d vòng/phút\n",
                               timestamp, rpm_val);
                    } else if (kind == 2) {
                        temp_val = value;
                        printf("[%s] TEMP  : %5d °C\n",
                               timestamp, temp_val);
                    }

                    /* In tổng hợp khi có đủ cả hai */
                    if (rpm_val >= 0 && temp_val >= 0) {
                        printf("[%s] ──── RPM=%d | Temp=%d°C ────\n\n",
                               timestamp, rpm_val, temp_val);
                        rpm_val  = -1;
                        temp_val = -1;
                    }
                } else {
                    /* Dòng không hợp lệ — log để debug */
                    get_timestamp(timestamp, sizeof(timestamp));
                    printf("[%s] [RAW] %s\n", timestamp, line_buf);
                }
            } else {
                /* Tích lũy ký tự */
                if (line_pos < LINE_BUF_SIZE - 1) {
                    line_buf[line_pos++] = c;
                }
            }
        }
    }

    printf("\n[INFO] Đóng cổng serial...\n");
    close(uart_fd);
    return EXIT_SUCCESS;
}
