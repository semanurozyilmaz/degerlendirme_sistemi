#include <stdio.h>

/* * Bu program kullanicidan alinan sayinin faktöriyelini hesaplar.
 * Negatif sayilar icin kontrol icerir.
 */
int main() {
    int n, i;
    unsigned long long factorial = 1;

    printf("Bir tamsayi giriniz: ");
    scanf("%d", &n);

    // Negatif sayi kontrolü
    if (n < 0)
        printf("Hata! Negatif sayilarin faktöriyeli hesaplanamaz.\n");
    else {
        // Faktöriyel hesaplama döngüsü
        for (i = 1; i <= n; ++i) {
            factorial *= i;
        }
        printf("%d sayisinin faktöriyeli = %llu\n", n, factorial);
    }

    return 0;
}