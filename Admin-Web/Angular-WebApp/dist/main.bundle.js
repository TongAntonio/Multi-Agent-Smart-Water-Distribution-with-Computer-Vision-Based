webpackJsonp(["main"],{

/***/ "../../../../../src/$$_lazy_route_resource lazy recursive":
/***/ (function(module, exports) {

function webpackEmptyAsyncContext(req) {
	// Here Promise.resolve().then() is used instead of new Promise() to prevent
	// uncatched exception popping up in devtools
	return Promise.resolve().then(function() {
		throw new Error("Cannot find module '" + req + "'.");
	});
}
webpackEmptyAsyncContext.keys = function() { return []; };
webpackEmptyAsyncContext.resolve = webpackEmptyAsyncContext;
module.exports = webpackEmptyAsyncContext;
webpackEmptyAsyncContext.id = "../../../../../src/$$_lazy_route_resource lazy recursive";

/***/ }),

/***/ "../../../../../src/app/app.component.css":
/***/ (function(module, exports, __webpack_require__) {

exports = module.exports = __webpack_require__("../../../../css-loader/lib/css-base.js")(false);
// imports


// module
exports.push([module.i, "", ""]);

// exports


/*** EXPORTS FROM exports-loader ***/
module.exports = module.exports.toString();

/***/ }),

/***/ "../../../../../src/app/app.component.html":
/***/ (function(module, exports) {

module.exports = "<nav class=\"navbar navbar-default navbar-static-top\" role=\"navigation\" style=\"margin-bottom: 0\">\n    <div class=\"navbar-header\">\n        <button type=\"button\" class=\"navbar-toggle\" data-toggle=\"collapse\" data-target=\".navbar-collapse\">\n            <span class=\"sr-only\">Toggle navigation</span>\n            <span class=\"icon-bar\"></span>\n            <span class=\"icon-bar\"></span>\n            <span class=\"icon-bar\"></span>\n        </button>\n        <a class=\"navbar-brand\">IOT 01418537</a>\n    </div>\n    <!-- /.navbar-header -->\n\n    <!-- /.navbar-top-links -->\n\n    <div class=\"navbar-default sidebar\" role=\"navigation\">\n        <div class=\"sidebar-nav navbar-collapse\">\n            <ul class=\"nav\" id=\"side-menu\">\n                <li>\n                    <a routerLink=\"/dashboard\"><i class=\"fa fa-dashboard fa-fw\"></i> Dashboard</a>\n                </li>\n                <li>\n                    <a routerLink=\"/report\"><i class=\"fa fa-table fa-fw\"></i> Report</a>\n                </li>\n            </ul>\n        </div>\n        <!-- /.sidebar-collapse -->\n    </div>\n    <!-- /.navbar-static-side -->\n</nav>\n\n<div id=\"page-wrapper\">\n        <router-outlet></router-outlet>\n</div>\n<!-- /#page-wrapper -->"

/***/ }),

/***/ "../../../../../src/app/app.component.ts":
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return AppComponent; });
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_0__angular_core__ = __webpack_require__("../../../core/esm5/core.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_1_angularfire2_database__ = __webpack_require__("../../../../angularfire2/database/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_2_angularfire2_auth__ = __webpack_require__("../../../../angularfire2/auth/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_3_rxjs_Observable__ = __webpack_require__("../../../../rxjs/_esm5/Observable.js");
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};




var AppComponent = (function () {
    function AppComponent(afAuth, db) {
        var _this = this;
        this.afAuth = afAuth;
        this.db = db;
        this.title = 'app';
        this.afAuth.auth.signInAnonymously();
        this.user = this.afAuth.authState;
        this.startHr = this.db.object('startHr').valueChanges();
        this.startMin = this.db.object('startMin').valueChanges();
        this.endHr = this.db.object('endHr').valueChanges();
        this.endMin = this.db.object('endMin').valueChanges();
        this.weight = this.db.object('weight').valueChanges();
        this.temperature = this.db.object('temperature').valueChanges();
        this.humidity = this.db.object('humidity').valueChanges();
        this.db.object('mode').valueChanges().subscribe(function (x) { return _this.mode = x; });
    }
    AppComponent.prototype.setTime = function (newStartHr, newStartMin, newEndHr, newEndMin) {
        this.db.object('startHr').set(newStartHr);
        this.db.object('startMin').set(newStartMin);
        this.db.object('endHr').set(newEndHr);
        this.db.object('endMin').set(newEndMin);
    };
    AppComponent.prototype.turnOnOff = function () {
        if (this.mode == 0) {
            this.db.object('mode').set(1);
        }
        else {
            this.db.object('mode').set(0);
        }
    };
    AppComponent.prototype.testOrder = function (val) {
        var _this = this;
        var promiseFn = this.db.object('testorder').set(val);
        //ให้ reset เป็น 0 เองอัตโนมัติหลังจากยิง command
        var source = __WEBPACK_IMPORTED_MODULE_3_rxjs_Observable__["a" /* Observable */].fromPromise(promiseFn);
        source.delay(10000).subscribe(function (x) { _this.db.object('testorder').set(0); });
    };
    AppComponent = __decorate([
        Object(__WEBPACK_IMPORTED_MODULE_0__angular_core__["n" /* Component */])({
            selector: 'app-root',
            template: __webpack_require__("../../../../../src/app/app.component.html"),
            styles: [__webpack_require__("../../../../../src/app/app.component.css")]
        }),
        __metadata("design:paramtypes", [__WEBPACK_IMPORTED_MODULE_2_angularfire2_auth__["a" /* AngularFireAuth */], __WEBPACK_IMPORTED_MODULE_1_angularfire2_database__["a" /* AngularFireDatabase */]])
    ], AppComponent);
    return AppComponent;
}());



/***/ }),

/***/ "../../../../../src/app/app.module.ts":
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* unused harmony export firebaseConfig */
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return AppModule; });
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_0__angular_platform_browser__ = __webpack_require__("../../../platform-browser/esm5/platform-browser.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_1__angular_core__ = __webpack_require__("../../../core/esm5/core.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_2__app_component__ = __webpack_require__("../../../../../src/app/app.component.ts");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_3__environments_environment__ = __webpack_require__("../../../../../src/environments/environment.ts");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_4_angularfire2__ = __webpack_require__("../../../../angularfire2/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_5_angularfire2_firestore__ = __webpack_require__("../../../../angularfire2/firestore/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_6_angularfire2_auth__ = __webpack_require__("../../../../angularfire2/auth/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_7_angularfire2_database__ = __webpack_require__("../../../../angularfire2/database/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_8__dashboard_dashboard_component__ = __webpack_require__("../../../../../src/app/dashboard/dashboard.component.ts");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_9__report_report_component__ = __webpack_require__("../../../../../src/app/report/report.component.ts");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_10__angular_router__ = __webpack_require__("../../../router/esm5/router.js");
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};




var firebaseConfig = __WEBPACK_IMPORTED_MODULE_3__environments_environment__["a" /* environment */].firebaseConfig;







var appRoutes = [
    { path: 'dashboard', component: __WEBPACK_IMPORTED_MODULE_8__dashboard_dashboard_component__["a" /* DashboardComponent */] },
    { path: 'report', component: __WEBPACK_IMPORTED_MODULE_9__report_report_component__["a" /* ReportComponent */] },
    { path: '**', component: __WEBPACK_IMPORTED_MODULE_8__dashboard_dashboard_component__["a" /* DashboardComponent */] }
];
var AppModule = (function () {
    function AppModule() {
    }
    AppModule = __decorate([
        Object(__WEBPACK_IMPORTED_MODULE_1__angular_core__["I" /* NgModule */])({
            declarations: [
                __WEBPACK_IMPORTED_MODULE_2__app_component__["a" /* AppComponent */],
                __WEBPACK_IMPORTED_MODULE_8__dashboard_dashboard_component__["a" /* DashboardComponent */],
                __WEBPACK_IMPORTED_MODULE_9__report_report_component__["a" /* ReportComponent */]
            ],
            imports: [
                __WEBPACK_IMPORTED_MODULE_0__angular_platform_browser__["a" /* BrowserModule */],
                __WEBPACK_IMPORTED_MODULE_4_angularfire2__["a" /* AngularFireModule */].initializeApp(firebaseConfig),
                __WEBPACK_IMPORTED_MODULE_5_angularfire2_firestore__["a" /* AngularFirestoreModule */],
                __WEBPACK_IMPORTED_MODULE_6_angularfire2_auth__["b" /* AngularFireAuthModule */],
                __WEBPACK_IMPORTED_MODULE_7_angularfire2_database__["b" /* AngularFireDatabaseModule */],
                __WEBPACK_IMPORTED_MODULE_10__angular_router__["a" /* RouterModule */].forRoot(appRoutes)
            ],
            providers: [],
            bootstrap: [__WEBPACK_IMPORTED_MODULE_2__app_component__["a" /* AppComponent */]]
        })
    ], AppModule);
    return AppModule;
}());



/***/ }),

/***/ "../../../../../src/app/dashboard/dashboard.component.css":
/***/ (function(module, exports, __webpack_require__) {

exports = module.exports = __webpack_require__("../../../../css-loader/lib/css-base.js")(false);
// imports


// module
exports.push([module.i, "", ""]);

// exports


/*** EXPORTS FROM exports-loader ***/
module.exports = module.exports.toString();

/***/ }),

/***/ "../../../../../src/app/dashboard/dashboard.component.html":
/***/ (function(module, exports) {

module.exports = "<div class=\"row\">\n    <div class=\"col-lg-12\">\n        <h1 class=\"page-header\">Dashboard</h1>\n    </div>\n    <!-- /.col-lg-12 -->\n</div>\n<!-- /.row -->\n<div class=\"row\">\n</div>\n<!-- /.row -->\n<div class=\"row\">\n    <div class=\"col-lg-8\">\n            <div class=\"col-lg-6 col-md-12\">\n                    <div class=\"panel panel-primary\">\n                        <div class=\"panel-heading\">\n                            <div class=\"row\">\n                                <div class=\"col-xs-3\">\n                                    <i class=\"fa fa-beer fa-5x\"></i>\n                                </div>\n                                <div class=\"col-xs-9 text-right\">\n                                    <div class=\"huge\">{{totalglass}}</div>\n                                    <div>แก้ว</div>\n                                </div>\n                            </div>\n                        </div>\n                        <a href=\"#\">\n                            <div class=\"panel-footer\">\n                                <span class=\"pull-left\">จำนวนแก้วที่ขายได้</span>\n                                <span class=\"pull-right\"><i class=\"fa fa-arrow-circle-right\"></i></span>\n                                <div class=\"clearfix\"></div>\n                            </div>\n                        </a>\n                    </div>\n                </div>\n                <div class=\"col-lg-6 col-md-12\">\n                    <div class=\"panel panel-green\">\n                        <div class=\"panel-heading\">\n                            <div class=\"row\">\n                                <div class=\"col-xs-3\">\n                                    <i class=\"fa fa-btc fa-5x\"></i>\n                                </div>\n                                <div class=\"col-xs-9 text-right\">\n                                    <div class=\"huge\">{{totalMoney}}</div>\n                                    <div>บาท</div>\n                                </div>\n                            </div>\n                        </div>\n                        <a href=\"#\">\n                            <div class=\"panel-footer\">\n                                <span class=\"pull-left\">จำนวนเงิน</span>\n                                <span class=\"pull-right\"><i class=\"fa fa-arrow-circle-right\"></i></span>\n                                <div class=\"clearfix\"></div>\n                            </div>\n                        </a>\n                    </div>\n                </div>\n                <div class=\"col-lg-6 col-md-12\">\n                    <div class=\"panel panel-yellow\">\n                        <div class=\"panel-heading\">\n                            <div class=\"row\">\n                                <div class=\"col-xs-3\">\n                                    <i class=\"fa fa-smile-o fa-5x\"></i>\n                                </div>\n                                <div class=\"col-xs-9 text-right\">\n                                    <div class=\"huge\">{{totalUser}}</div>\n                                    <div>คน</div>\n                                </div>\n                            </div>\n                        </div>\n                        <a href=\"#\">\n                            <div class=\"panel-footer\">\n                                <span class=\"pull-left\">จำนวนลูกค้า</span>\n                                <span class=\"pull-right\"><i class=\"fa fa-arrow-circle-right\"></i></span>\n                                <div class=\"clearfix\"></div>\n                            </div>\n                        </a>\n                    </div>\n                </div>\n                <div class=\"col-lg-6 col-md-12\">\n                    <div class=\"panel\" [ngClass]=\"{'panel-green': mode, 'panel-red': !mode}\">\n                        <div class=\"panel-heading\">\n                            <div class=\"row\">\n                                <div class=\"col-xs-3\">\n                                    <i class=\"fa fa-tasks fa-5x\"></i>\n                                </div>\n                                <div class=\"col-xs-9 text-right\">                                         \n                                    <div *ngIf=\"mode==0\" class=\"huge\">OFF</div>\n                                    <div *ngIf=\"mode==1\" class=\"huge\">ON</div>\n                                    <button (click)=\"turnOnOff()\" type=\"button\" class=\"btn btn-info\"><i class=\"fa fa-power-off\"></i></button>\n                                </div>\n                            </div>\n                        </div>\n                        <a href=\"#\">\n                            <div class=\"panel-footer\">\n                                <span class=\"pull-left\">สถานะเครื่อง</span>\n                                <span class=\"pull-right\"><i class=\"fa fa-arrow-circle-right\"></i></span>\n                                <div class=\"clearfix\"></div>\n                            </div>\n                        </a>\n                    </div>\n                </div>\n                <div class=\"col-lg-6 col-md-12\">\n                    <div class=\"panel panel-success\">\n                        <div class=\"panel-heading\">\n                            Sensor (Real-Time) \n                        </div>\n                        <div class=\"panel-body\">\n                                <div class=\"list-group\">\n                                        <a href=\"#\" class=\"list-group-item\">\n                                            <i class=\"fa fa-ellipsis-v fa-fw\"></i> ระดับน้ำ (Raw Data)\n                                            <span class=\"pull-right text-muted small\"><em>{{weight | async}}</em>\n                                            </span>\n                                        </a>\n                                        <a href=\"#\" class=\"list-group-item\">\n                                            <i class=\"fa fa-ellipsis-v fa-fw\"></i> ระดับน้ำ\n                                            <span class=\"pull-right text-muted small\"><em>{{waterlevel | async}} %</em>\n                                            </span>\n                                        </a>\n                                        <a href=\"#\" class=\"list-group-item\">\n                                            <i class=\"fa fa-sun-o fa-fw\"></i> อุณหภูมิ\n                                            <span class=\"pull-right text-muted small\"><em>{{temperature | async}} c</em>\n                                            </span>\n                                        </a>\n                                        <a href=\"#\" class=\"list-group-item\">\n                                            <i class=\"fa fa-tint fa-fw\"></i> ความชื้น\n                                            <span class=\"pull-right text-muted small\"><em>{{humidity | async}} %</em>\n                                            </span>\n                                        </a>\n                                    </div>            \n                        </div>\n                    </div>\n                </div>\n    </div>\n    <!-- /.col-lg-8 -->\n    <div class=\"col-lg-4\">\n        <div class=\"panel panel-default\">\n            <div class=\"panel-heading\">\n               เวลาขาย\n            </div>\n            <!-- /.panel-heading -->\n            <div class=\"panel-body\">\n                    <div class=\"alert alert-success\">\n                           <h3> <i class=\"fa fa-clock-o fa-fw\"></i> {{startHr | async}}.{{startMin | async}} - {{endHr | async}}.{{endMin | async}}</h3>\n                    </div>\n                    <div class=\"panel panel-primary\">\n                            <div class=\"panel-heading\">\n                                ตั้งเวลา\n                            </div>\n                            <div class=\"panel-body\">                                   \n                                    <form role=\"form\">\n                                        <label>เริ่ม</label>\n                                        <div class=\"form-group input-group\">\n                                            <input #in1 type=\"text\" class=\"form-control\">\n                                            <span class=\"input-group-addon\">น.</span>\n                                        </div>\n                                        <div class=\"form-group input-group\">\n                                                <input #in2  type=\"text\" class=\"form-control\">\n                                                <span class=\"input-group-addon\">นาที</span>\n                                        </div>\n                                        <label>ถึง</label>\n                                        <div class=\"form-group input-group\">\n                                                <input #in3  type=\"text\" class=\"form-control\">\n                                                <span class=\"input-group-addon\">น.</span>\n                                        </div>\n                                        <div class=\"form-group input-group\">\n                                                <input #in4  type=\"text\" class=\"form-control\">\n                                                <span class=\"input-group-addon\">นาที</span>\n                                        </div>\n                                    </form>                                        \n                             </div>\n                            <div class=\"panel-footer\">\n                                    <button (click)=\"setTime(in1.value,in2.value,in3.value,in4.value)\" class=\"btn btn-primary btn-block\">Save</button>\n                            </div>\n                    </div>\n            </div>\n            <!-- /.panel-body -->\n        </div>\n    </div>\n    <!-- /.col-lg-4 -->\n</div>\n<!-- /.row -->\n"

/***/ }),

/***/ "../../../../../src/app/dashboard/dashboard.component.ts":
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return DashboardComponent; });
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_0__angular_core__ = __webpack_require__("../../../core/esm5/core.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_1_angularfire2_database__ = __webpack_require__("../../../../angularfire2/database/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_2_angularfire2_auth__ = __webpack_require__("../../../../angularfire2/auth/index.js");
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};



var DashboardComponent = (function () {
    function DashboardComponent(afAuth, db) {
        this.afAuth = afAuth;
        this.db = db;
        this.title = 'app';
        this.afAuth.auth.signInAnonymously();
        this.user = this.afAuth.authState;
    }
    DashboardComponent.prototype.ngOnInit = function () {
        var _this = this;
        this.startHr = this.db.object('/setting/startHr').valueChanges();
        this.startMin = this.db.object('/setting/startMin').valueChanges();
        this.endHr = this.db.object('/setting/endHr').valueChanges();
        this.endMin = this.db.object('/setting/endMin').valueChanges();
        this.weight = this.db.object('/sensor/weight').valueChanges();
        this.temperature = this.db.object('/sensor/temperature').valueChanges();
        this.humidity = this.db.object('/sensor/humidity').valueChanges();
        this.waterlevel = this.db.object('/sensor/waterlevel').valueChanges();
        this.db.object('/setting/mode').valueChanges().subscribe(function (x) { return _this.mode = x; });
        this.records$ = this.db.list('/records').valueChanges();
        this.records$.subscribe(function (datas) {
            var user = [];
            _this.totalglass = 0;
            _this.totalMoney = 0;
            for (var i = 0; i < datas.length; i++) {
                var p = datas[i].split('|');
                var p0 = p[0];
                var p1 = +p[1];
                var p2 = +p[2];
                user.push(p0);
                _this.totalglass++;
                _this.totalMoney += p1;
            }
            var unique = user.filter(function (v, i, a) { return a.indexOf(v) === i; });
            _this.totalUser = unique.length;
        });
    };
    DashboardComponent.prototype.setTime = function (newStartHr, newStartMin, newEndHr, newEndMin) {
        this.db.object('/setting/startHr').set(newStartHr);
        this.db.object('/setting/startMin').set(newStartMin);
        this.db.object('/setting/endHr').set(newEndHr);
        this.db.object('/setting/endMin').set(newEndMin);
    };
    DashboardComponent.prototype.turnOnOff = function () {
        if (this.mode == 0) {
            this.db.object('/setting/mode').set(1);
        }
        else {
            this.db.object('/setting/mode').set(0);
        }
    };
    DashboardComponent = __decorate([
        Object(__WEBPACK_IMPORTED_MODULE_0__angular_core__["n" /* Component */])({
            selector: 'app-dashboard',
            template: __webpack_require__("../../../../../src/app/dashboard/dashboard.component.html"),
            styles: [__webpack_require__("../../../../../src/app/dashboard/dashboard.component.css")]
        }),
        __metadata("design:paramtypes", [__WEBPACK_IMPORTED_MODULE_2_angularfire2_auth__["a" /* AngularFireAuth */], __WEBPACK_IMPORTED_MODULE_1_angularfire2_database__["a" /* AngularFireDatabase */]])
    ], DashboardComponent);
    return DashboardComponent;
}());



/***/ }),

/***/ "../../../../../src/app/report/report.component.css":
/***/ (function(module, exports, __webpack_require__) {

exports = module.exports = __webpack_require__("../../../../css-loader/lib/css-base.js")(false);
// imports


// module
exports.push([module.i, "", ""]);

// exports


/*** EXPORTS FROM exports-loader ***/
module.exports = module.exports.toString();

/***/ }),

/***/ "../../../../../src/app/report/report.component.html":
/***/ (function(module, exports) {

module.exports = "<div class=\"row\">\n    <div class=\"col-lg-12\">\n        <h1 class=\"page-header\">Report</h1>\n    </div>\n    <!-- /.col-lg-12 -->\n</div>\n<!-- /.row -->\n<div class=\"row\">\n    <table class=\"table\">\n            <thead>\n              <tr>\n                <th>UserName</th>\n                <th>Order</th>\n                <th>Time</th>\n              </tr>\n            </thead>\n            <tbody *ngFor=\"let item of records\">\n              <tr>\n                <td>{{item.name}}</td>\n                <td>{{item.order}}</td>\n                <td>{{item.time}}</td>\n            </tr>\n            </tbody>\n          </table>\n</div>\n<!-- /.row -->\n<div class=\"row\">\n\n</div>\n<!-- /.row -->\n"

/***/ }),

/***/ "../../../../../src/app/report/report.component.ts":
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return ReportComponent; });
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_0__angular_core__ = __webpack_require__("../../../core/esm5/core.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_1_angularfire2_database__ = __webpack_require__("../../../../angularfire2/database/index.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_2_angularfire2_auth__ = __webpack_require__("../../../../angularfire2/auth/index.js");
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};



var ReportComponent = (function () {
    function ReportComponent(afAuth, db) {
        this.afAuth = afAuth;
        this.db = db;
        this.afAuth.auth.signInAnonymously();
        this.user = this.afAuth.authState;
    }
    ReportComponent.prototype.ngOnInit = function () {
        var _this = this;
        this.records$ = this.db.list('/records').valueChanges();
        this.records$.subscribe(function (datas) {
            var a = [];
            for (var i = 0; i < datas.length; i++) {
                console.log(datas[i]);
                var p = datas[i].split('|');
                var p0 = p[0];
                var p1 = +p[1];
                var p2 = +p[2];
                a.push({ name: p0, order: p1, time: new Date(p2 * 1000) });
            }
            _this.records = a;
        });
    };
    ReportComponent = __decorate([
        Object(__WEBPACK_IMPORTED_MODULE_0__angular_core__["n" /* Component */])({
            selector: 'app-report',
            template: __webpack_require__("../../../../../src/app/report/report.component.html"),
            styles: [__webpack_require__("../../../../../src/app/report/report.component.css")]
        }),
        __metadata("design:paramtypes", [__WEBPACK_IMPORTED_MODULE_2_angularfire2_auth__["a" /* AngularFireAuth */], __WEBPACK_IMPORTED_MODULE_1_angularfire2_database__["a" /* AngularFireDatabase */]])
    ], ReportComponent);
    return ReportComponent;
}());



/***/ }),

/***/ "../../../../../src/environments/environment.ts":
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "a", function() { return environment; });
// The file contents for the current environment will overwrite these during build.
// The build system defaults to the dev environment which uses `environment.ts`, but if you do
// `ng build --env=prod` then `environment.prod.ts` will be used instead.
// The list of which env maps to which file can be found in `.angular-cli.json`.
var environment = {
    production: false,
    firebaseConfig: {
        apiKey: "AIzaSyBCwsCzk7lcHVO2YNF1DS3lMRU62_uImYs",
        authDomain: "myiot-68b0f.firebaseapp.com",
        databaseURL: "https://myiot-68b0f.firebaseio.com",
        projectId: "myiot-68b0f",
        storageBucket: "myiot-68b0f.appspot.com",
        messagingSenderId: "406883477674"
    }
};


/***/ }),

/***/ "../../../../../src/main.ts":
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
Object.defineProperty(__webpack_exports__, "__esModule", { value: true });
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_0__angular_core__ = __webpack_require__("../../../core/esm5/core.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_1__angular_platform_browser_dynamic__ = __webpack_require__("../../../platform-browser-dynamic/esm5/platform-browser-dynamic.js");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_2__app_app_module__ = __webpack_require__("../../../../../src/app/app.module.ts");
/* harmony import */ var __WEBPACK_IMPORTED_MODULE_3__environments_environment__ = __webpack_require__("../../../../../src/environments/environment.ts");




if (__WEBPACK_IMPORTED_MODULE_3__environments_environment__["a" /* environment */].production) {
    Object(__WEBPACK_IMPORTED_MODULE_0__angular_core__["_12" /* enableProdMode */])();
}
Object(__WEBPACK_IMPORTED_MODULE_1__angular_platform_browser_dynamic__["a" /* platformBrowserDynamic */])().bootstrapModule(__WEBPACK_IMPORTED_MODULE_2__app_app_module__["a" /* AppModule */])
    .catch(function (err) { return console.log(err); });


/***/ }),

/***/ 0:
/***/ (function(module, exports, __webpack_require__) {

module.exports = __webpack_require__("../../../../../src/main.ts");


/***/ })

},[0]);
//# sourceMappingURL=main.bundle.js.map